import os

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
    geoserver_workspace: str = "general"
    geoserver_tif_folder: str = "geotiff"
    geoserver_imagemosaic_folder: str = "imagemosaic"

    @property
    def app_version(self):
        return __version__

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

    def oauth_login_url(self):
        return f"{self.oauth_url}/api/login"

    def oauth_body(self):
        return {
            "loginId": self.oauth_user,
            "password": self.oauth_pwd,
            "applicationId": self.oauth_app_id,
            "noJWT": False,
        }

    def oauth_headers(self):
        return {
            "Authorization": self.oauth_api_key,
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
        return os.path.join(self.geoserver_data_dir, "temp")


settings = ProjectSettings()
settings = ProjectSettings()
