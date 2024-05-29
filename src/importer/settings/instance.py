import os

import yaml
from pydantic import BaseSettings

from importer.version import __version__


class ProjectSettings(BaseSettings):

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # Importer settings
    delete_after_days: int = 0  # if 0, never delete
    delete_after_count: int = 0  # if 0, never delete

    # Webserver settings
    api_title: str = "Importer & Mapper API"
    api_description: str = None
    app_log_level: str = "info"
    app_log_format: str = "[%(asctime)s] %(levelname)s - %(name)s: %(message)s"
    api_key: str

    # Broker settings
    rabbitmq_host: str
    rabbitmq_port: str
    rabbitmq_user: str
    rabbitmq_pass: str
    rabbitmq_ca_cert_file: str
    rabbitmq_cert_file: str
    rabbitmq_key_file: str
    rabbitmq_vhost: str

    rabbitmq_exchange: str
    rabbitmq_exchange_type: str
    rabbitmq_input_queue: str
    rabbitmq_report_routingkey_prefix: str

    # Data Lake settings
    ckan_url: str
    oauth_url: str
    oauth_api_key: str
    oauth_app_id: str
    oauth_user: str
    oauth_pwd: str
    oauth2_settings: dict = None

    # Database settings
    database_host: str
    database_port: str
    database_name: str
    database_user: str
    database_pass: str

    # Geoserver settings
    geoserver_admin_user: str
    geoserver_admin_password: str
    geoserver_data_dir: str
    use_https: bool = False
    geoserver_host: str
    geoserver_port: str
    geoserver_workspace: str = "general"
    geoserver_tif_folder: str = "geotiff"
    geoserver_imagemosaic_folder: str = "imagemosaic"

    @property
    def app_version(self):
        return __version__

    def get_service_url(self):
        protocol = "https" if self.use_https else "http"
        return f"{protocol}://{self.geoserver_host}:{self.geoserver_port}/geoserver"

    def get_rabbitmq_consumer_routing(self):
        return {
            "exchange": self.rabbitmq_exchange,
            "exchange_type": self.rabbitmq_exchange_type,
            "queue": self.rabbitmq_input_queue,
        }

    def get_rabbitmq_producer_routing(self, routing_suffix: str):
        return {
            "exchange": self.rabbitmq_exchange,
            "exchange_type": self.rabbitmq_exchange_type,
            "routing_key": self.rabbitmq_report_routingkey_prefix + routing_suffix,
        }

    def database_url(self):
        return (
            f"postgresql://{self.database_user}:{self.database_pass}@"
            f"{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @staticmethod
    def safe_access(dictionary, keys, default=None):
        """
        Safely access nested items in a dictionary.

        Args:
            dictionary (dict): The dictionary to access.
            keys (list): List of keys to access the nested item.
            default: Default value to return if any key is missing. Defaults to None.

        Returns:
            The value at the nested keys if they exist, otherwise the default value.
        """
        try:
            for key in keys:
                dictionary = dictionary[key]
            return dictionary
        except (KeyError, TypeError):
            return default

    def get_oauth_setting(self, project_name, setting):
        if not self.oauth2_settings:
            yaml_file = "/src/importer/secrets.yml"
            if os.path.isfile(yaml_file):
                with open(yaml_file) as f:
                    data = yaml.safe_load(f)
                    self.oauth2_settings = data.get("projects")
        try:
            return self.oauth2_settings.get(project_name).get(setting)
        except (TypeError, KeyError, AttributeError):
            return None

    def oauth_login_url(self, project_name: str = None):
        oauth_url = self.get_oauth_setting(project_name, "oauth_url") or self.oauth_url
        return f"{oauth_url}/api/login"

    def oauth_body(self, project_name: str = None):
        return {
            "loginId": self.get_oauth_setting(project_name, "oauth_user") or self.oauth_url,
            "password": self.get_oauth_setting(project_name, "oauth_pwd") or self.oauth_pwd,
            "applicationId": self.get_oauth_setting(project_name, "oauth_app_id") or self.oauth_app_id,
            "noJWT": False,
        }

    def oauth_headers(self, project_name: str = None):
        return {
            "Authorization": self.get_oauth_setting(project_name, "oauth_app_key") or self.oauth_api_key,
        }

    def data_lake_resource_show_url(self):
        return f"{self.ckan_url}/api/3/action/resource_show"

    def data_lake_resource_delete(self):
        return f"{self.ckan_url}/api/3/action/resource_delete"

    def data_lake_dataset_delete_url(self):
        return f"{self.ckan_url}/api/3/action/package_delete"

    def data_lake_dataset_show_url(self):
        return f"{self.ckan_url}/api/3/action/package_show"

    @staticmethod
    def data_lake_headers(access_token: str):
        return {
            "Authorization": f"Bearer {access_token}",
        }

    def get_temp_folder(self):
        temp_folder = os.path.join(self.geoserver_data_dir, "temp")
        if not os.path.exists(temp_folder):
            os.makedirs(temp_folder)
        return temp_folder


settings = ProjectSettings()
