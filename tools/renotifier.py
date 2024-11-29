import datetime
import json
import os
import ssl
from enum import Enum
from json import JSONEncoder

import pika
import requests
import validators
from dotenv import load_dotenv
from requests import HTTPError

load_dotenv("tools/dev.env")

# Subclass JSONEncoder
class DateTimeEncoder(JSONEncoder):
    # Override the default method
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()


class DeliveryMode(Enum):
    TRANSIENT = 1
    PERSISTENT = 2


class SettingsLoader:
    @staticmethod
    def load_certificates(settings):
        """Load certificate paths from the provided settings."""
        ca_file = settings.get("RABBITMQ_CA_CERT_FILE")
        cert_file = settings.get("RABBITMQ_CERT_FILE")
        key_file = settings.get("RABBITMQ_KEY_FILE")
        return ca_file, cert_file, key_file


class Sender:
    @staticmethod
    def get_tls_parameters(host, ca_file, cert_file, key_file):
        """Set up SSL options with the provided certificate files."""
        ssl_context = ssl.create_default_context(cafile=ca_file)
        ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
        return pika.SSLOptions(ssl_context, host)


class Notify:

    def __init__(self):
        # Load environment settings
        self.settings = {
            "hostname": os.getenv('RABBITMQ_HOST'),
            "port": int(os.getenv('RABBITMQ_PORT')),
            "vhost": os.getenv('RABBITMQ_VHOST'),
            "exchange": os.getenv('RABBITMQ_EXCHANGE'),
            "exchange_type": os.getenv('RABBITMQ_EXCHANGE_TYPE'),
            "queue_name": os.getenv('RABBITMQ_INPUT_QUEUE'),
            "rk_prefix": os.getenv('RK_PREFIX'),
            "RABBITMQ_CA_CERT_FILE": os.getenv('RABBITMQ_CA_CERT_FILE'),
            "RABBITMQ_CERT_FILE": os.getenv('RABBITMQ_CERT_FILE'),
            "RABBITMQ_KEY_FILE": os.getenv('RABBITMQ_KEY_FILE'),
            "app_id": os.getenv('OAUTH_APP_ID'),
            "datacatalog_host": os.getenv('SITE_URL'),
            "geoserver_url": os.getenv('GEOSERVER_URL'),
            "oauth_url": os.getenv("OAUTH_URL"),
            "oauth_user": os.getenv('OAUTH_USER'),
            "oauth_pwd": os.getenv('OAUTH_PWD'),
            "oauth_apikey": os.getenv('OAUTH_API_KEY'),
        }
        
        # Setup connection parameters with SSL using the static method
        self.parameters = Notify.get_connection(self.settings)
        print("pika connection using %s" % self.parameters)
        self.access_token = self.get_access_token()

    @staticmethod
    def get_connection(settings):
        """Static method to initialize pika.ConnectionParameters with SSL options."""
        ca_file, cert_file, key_file = SettingsLoader.load_certificates(settings)
        credentials = pika.credentials.ExternalCredentials()
        host = settings["hostname"]
        ssl_options = Sender.get_tls_parameters(host, ca_file, cert_file, key_file)
        
        parameters = pika.ConnectionParameters(
            credentials=credentials,
            host=host,
            port=settings["port"],
            virtual_host=settings["vhost"],
            ssl_options=ssl_options,
        )
        return parameters

    def send_notification(self, data_id, output, req_code=None):
        connection = pika.BlockingConnection(self.parameters)
        channel = connection.channel()
        
        # Declare the exchange with the given type
        channel.queue_bind(exchange=self.settings["exchange"], queue=self.settings["queue_name"], routing_key=f'{self.settings["rk_prefix"]}.#')

        properties = pika.BasicProperties(
            content_type='application/json',
            content_encoding='utf-8',
            **self.get_properties()
        )

        routing_key = f'{self.settings["rk_prefix"]}.{data_id}'
        if req_code:
            routing_key = f'{routing_key}.{req_code}'

        channel.basic_publish(
            exchange=self.settings["exchange"],
            routing_key=routing_key,
            body=output,
            properties=properties
        )
        channel.close()
        connection.close()


    def get_req_code(self, dataset_dict):
        req_code = None
        if dataset_dict.get('external_attributes'):
            ext_attr = dataset_dict.get('external_attributes')
            req_code = ext_attr.get('request_code', None)
        return req_code

    def build_dict(self, pkg_dict, ix, action, dataset_dict):
        if dataset_dict.get('spatial', 'None'):
            geometry = json.loads(dataset_dict.get('spatial', 'None'))
        else:
            geometry = ""

        req_code = self.get_req_code(dataset_dict)
        if not req_code:
            req_code = ''

        url = pkg_dict.get('url')
        if not validators.url(url):
            url = f"{self.settings['datacatalog_host']}/dataset/{dataset_dict.get('id','None')}/resource/"\
                f"{pkg_dict.get('id', 'None')}/download/{url}"
        
        output_dict = {
            "metadata_id": dataset_dict.get("id", 'None'),
            "id": pkg_dict.get("id", 'None'),
            "datatype_id": ix,
            "type": action,
            "name": pkg_dict.get('name', None),
            "creation_date": dataset_dict.get('temporalReference_dateOfCreation', 'None'),
            "start_date": pkg_dict.get('file_date_start', 'None'),
            "end_date": pkg_dict.get('file_date_end', 'None'),
            "geometry": geometry,
            "destinatary_organization": pkg_dict.get('organization', 'None'),
            "request_code": req_code,
            "url": url
        }
        return json.dumps(output_dict, cls=DateTimeEncoder)


    def get_properties(self):
        return {
            'delivery_mode': DeliveryMode.PERSISTENT.value,
            'app_id': self.settings["app_id"]
        }


    def get_access_token(self):
        url = f'{self.settings["oauth_url"]}/api/login'
        body = {
            "loginId": self.settings["oauth_user"],
            "password": self.settings["oauth_pwd"],
            "applicationId": self.settings["app_id"],
            "noJWT": False
        }
        headers = {
            "Authorization": self.settings["oauth_apikey"]
        }
        try:
            response = requests.post(url, json=body, headers=headers)
            response.raise_for_status()
        except HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")
        except Exception as err:
            print(f"Other error occurred: {err}")
        else:
            print("Access Token obtained")
        if response.status_code == 200:
            REFRESH_TOKEN = response.json()["refreshToken"]
        else:
            print('Error:')
            print(response.json())
            raise Exception
        return response.json()["token"]


    def package_search(self, body):
        url = f'{self.settings["datacatalog_host"]}/api/action/package_search'
        headers = {
            "Authorization": f'Bearer {self.access_token}',
        }
        try:
            response = requests.post(url, json=body, headers=headers)
            if response.status_code != 200:
                print('Error:')
                print(response.json())
                raise Exception
        except Exception as e:
            print("Error occurred: " + str(e))

        try:
            result = response.json().get('result')
            pkg_dict_list = result.get('results')
        except KeyError as ke:
            print("Result not found" + ke)
        
        return pkg_dict_list
        

    def query(self, datatype_id, rows=10):
        body = dict()
        body["fq_list"] = [f"datatype_id:{datatype_id}"]
        body['include_private'] = True
        body['rows'] = rows
        return self.package_search(body)
    

    def start_import(self, datatype_ids, rows=1):
        for id in datatype_ids:
            result_list = self.query(id, rows=rows)
            for dataset_dict in result_list:
                if not dataset_dict.get('resources'):
                    print('dataset without resources')
                    continue
                for resource_dict in dataset_dict.get('resources'):
                    output = self.build_dict(resource_dict, id, "update", dataset_dict)
                    print('sending notification...')
                    self.send_notification(id, output)


# Example usage
datatype_ids = [11001]
notify = Notify()
notify.start_import(datatype_ids, rows=1)
