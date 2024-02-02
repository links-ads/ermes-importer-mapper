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

load_dotenv()

# subclass JSONEncoder
class DateTimeEncoder(JSONEncoder):
    #Override the default method
    def default(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return obj.isoformat()


class DeliveryMode(Enum):
    TRANSIENT = 1
    PERSISTENT = 2


class Notify:

    def __init__(self):
        self.port = int(os.getenv('MQ_PORT'))
        self.userid = os.getenv('MQ_USERID')
        self.password = os.getenv('MQ_PWD')
        self.hostname = os.getenv('MQ_HOSTNAME')
        self.vhost = os.getenv('MQ_VHOST')
        self.exchange_name = os.getenv('MQ_EXCHANGE_NAME')
        self.queue_name = os.getenv('MQ_QUEUE')
        self.app_id = os.getenv('MQ_APPID')
        self.datacatalog_host = os.getenv('SITE_URL')

        self.oauth_url = os.getenv("OAUTH_URL")
        self.oauth_user = os.getenv('OAUTH_USER')
        self.oauth_pwd = os.getenv('OAUTH_PWD')
        self.oauth_appid = os.getenv('OAUTH_APP_ID')
        self.oauth_apikey = os.getenv('OAUTH_APIKEY')
        self.rk_prefix = os.getenv('RK_PREFIX')

        self.credentials = pika.PlainCredentials(self.userid, self.password)
        self.ssl_options = pika.SSLOptions(ssl.create_default_context(), self.hostname)
        self.parameters = pika.ConnectionParameters(host=self.hostname, virtual_host=self.vhost,
                                                    credentials=self.credentials, port=self.port,
                                                    ssl_options=self.ssl_options)
        print("pika connection using %s" % self.parameters)
        self.access_token = self.get_access_token()
        
    
    def send_notification(self, data_id, output, req_code=None):
        connection = pika.BlockingConnection(self.parameters)
        channel = connection.channel()
        channel.queue_bind(exchange=self.exchange_name, queue=self.queue_name, routing_key=f'{self.rk_prefix}.#')
        properties = pika.BasicProperties(
            content_type='application/json',
            content_encoding='utf-8',
            **self.get_properties())

        routing_key = f'{self.rk_prefix}.{data_id}'
        if req_code:
            routing_key = f'{routing_key}.{req_code}'

        channel.basic_publish(exchange=self.exchange_name,
                            routing_key=routing_key, body=output,
                            properties=properties)
        channel.close()
        connection.close()


    def get_req_code(self, dataset_dict):
        req_code = None
        if dataset_dict.get('external_attributes'):
            ext_attr = dataset_dict.get('external_attributes')
            req_code = ext_attr.get('request_code', None)
        return req_code

    def build_dict(self, pkg_dict, ix, action, dataset_dict):
        # retrieve 
        if dataset_dict.get('spatial', 'None'):
            geometry = json.loads(dataset_dict.get('spatial', 'None'))
        else:
            geometry = ""

        req_code = self.get_req_code(dataset_dict)
        if not req_code:
            req_code = ''

        url = pkg_dict.get('url')
        if not validators.url(url):
            url = f"{self.datacatalog_host}/dataset/{dataset_dict.get('id','None')}/resource/"\
                f"{pkg_dict.get('id', 'None')}/download/{url}"
        
        output_dict = {
            "metadata_id": dataset_dict.get("id",'None'),
            "id": pkg_dict.get("id", 'None'),
            "datatype_id": ix,
            "type": action,
            "creation_date": dataset_dict.get('temporalReference_dateOfCreation', 'None'),
            "start_date": pkg_dict.get('file_date_start', 'None'),
            "end_date": pkg_dict.get('file_date_end', 'None'),
            "geometry": geometry,
            "request_code": req_code,
            "url": url
            }
        return json.dumps(output_dict, cls=DateTimeEncoder)


    def get_properties(self):
        return {
            'delivery_mode': DeliveryMode.PERSISTENT.value,
            'app_id': self.app_id,
            'user_id': self.userid
        }


    def get_access_token(self):
        url = f'{self.oauth_url}/api/login'
        body = {
            "loginId": self.oauth_user,
            "password": self.oauth_pwd,
            "applicationId": self.oauth_appid,
            "noJWT" : False
        }
        headers = {
            "Authorization": self.oauth_apikey
        }
        try:
            response = requests.post(url, json=body, headers=headers)
            # If the response was successful, no Exception will be raised
            response.raise_for_status()
        except HTTPError as http_err:
            print(f"HTTP error occurred: {http_err}")  # Python 3.6
        except Exception as err:
            print(f"Other error occurred: {err}")  # Python 3.6
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
        url = f'{self.datacatalog_host}/api/action/package_search'
        headers = {
            "Authorization": f'Bearer {self.access_token}',
        }
        try:
            response = requests.post(url,
                        json=body,
                        headers=headers)
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


datatype_ids = []

notify = Notify()
notify.start_import(datatype_ids, rows=1)
