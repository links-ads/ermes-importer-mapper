import base64
import datetime
import io
import json
import logging
from typing import Optional

import requests
from requests.models import HTTPError

from importer.settings.instance import settings

LOG = logging.getLogger(__name__)


class DataLakeDriver:
    """Driver that manages the authentication with the Data Lake using oauth"""

    def __init__(self):
        self.access_token_url = settings.oauth_login_url()
        self.access_token_body = settings.oauth_body()
        self.access_token_headers = settings.oauth_headers()

        self.access_token = None
        self.access_token_expiration = None

    def get_access_token(self) -> tuple:
        response = requests.post(self.access_token_url, json=self.access_token_body, headers=self.access_token_headers)
        response.raise_for_status()
        if response.status_code // 100 == 2:
            resp_as_dict = response.json()
            token, refresh_token = resp_as_dict["token"], resp_as_dict["refreshToken"]

            token_payload = token.split(".")[1]
            token_payload = base64.b64decode(token_payload + "==").decode("utf-8")
            expiration_timestamp = json.loads(token_payload)["exp"]
            token_expiration = datetime.datetime.utcfromtimestamp(expiration_timestamp) - datetime.timedelta(
                minutes=10
            )
            LOG.debug("Data Lake Access Token obtained")
            return token, refresh_token, token_expiration
        raise Exception(response.json())

    def set_access_token(self):
        if self.access_token is None or datetime.datetime.utcnow() > self.access_token_expiration:
            self.access_token, _, self.access_token_expiration = self.get_access_token()

    def get(self, resource_id: str, resource_url: Optional[str]):
        self.set_access_token()
        try:
            return self.get_implement(resource_id, resource_url)
        except HTTPError:
            self.access_token, _, self.access_token_expiration = self.get_access_token()
            return self.get_implement(resource_id, resource_url)

    def get_implement(self, resource_id, resource_url):
        if resource_url is None:  # if resource_url is not provided, retrieve it from data lake using the resource_id
            response = requests.get(
                settings.data_lake_resource_show_url(),
                params={"id": resource_id},
                headers=settings.data_lake_headers(self.access_token),
            )
            response.raise_for_status()
            if response.status_code // 100 == 2:
                resp_as_dict = response.json()
                resource_url = resp_as_dict["result"]["url"]
                LOG.debug(f"Data Lake resource with id {resource_id} obtained")
        LOG.info(f"Downloading resource from {resource_url}")
        return requests.get(resource_url, headers=settings.data_lake_headers(self.access_token)), resource_url

    def get_metadata(self, metadata_id: str, include_private=True):
        """Retrieve from the datalake the metadata assosiated with a given metadata_id
        :param metadata_id: string containing the metadata_id associated with the layer
        """
        self.set_access_token()
        metadata = None
        if metadata_id:
            response = requests.get(
                settings.data_lake_dataset_show_url(),
                params={"id": metadata_id, "include_private": include_private},
                headers=settings.data_lake_headers(self.access_token),
            )
            if response.status_code // 100 == 2:
                resp_as_dict = response.json()
                metadata = resp_as_dict["result"]
                LOG.debug(f"Data Lake dataset with id {metadata_id} obtained")
            else:
                LOG.error("Data Lake dataset with id cannot be retrieved")
                LOG.error(response)

        return metadata

    def download_resource(self, resource_id: str, include_private=True):
        """Retrieve from the datalake the resource file
        :param resource_id: string containing the resource_id associated with the layer
        """
        r, url = self.get(resource_id=resource_id, resource_url=None)
        return io.BytesIO(r.content), url.split("/")[-1]

        # get resource
        # url=result['result']['url']
        # return response.content
        # file_ = None
        # if resource_id:
        #     response = requests.get(settings.data_lake_dataset_show_url(), params={"id": metadata_id,
        #       "include_private": include_private}, headers=settings.data_lake_headers(self.access_token))
        #     if response.status_code // 100 == 2:
        #         resp_as_dict = response.json()
        #         metadata = resp_as_dict["result"]
        #         LOG.debug(f'Data Lake dataset with id {metadata_id} obtained')
        #     else:
        #         LOG.error(f'Data Lake dataset with id cannot be retrieved')
        #         LOG.error(response)

        # return metadata

    def is_dataset_empty(self, metadata_id: str, include_private=True):
        self.set_access_token()

        metadata = self.get_metadata(metadata_id=metadata_id, include_private=include_private)
        if not metadata.get("resources"):
            LOG.info("dataset without resources")
            return True

        return False

    def delete_dataset(self, metadata_id: str, include_private=True):
        self.set_access_token()

        response = requests.post(
            settings.data_lake_dataset_delete_url(),
            json={"id": metadata_id},
            headers=settings.data_lake_headers(self.access_token),
        )
        if response.status_code // 100 == 2:
            resp_as_dict = response.json()
            LOG.info(f"Data Lake metadata with id {metadata_id} deleted: {resp_as_dict}")

        else:
            LOG.error(f"Data Lake metadata with id {metadata_id} cannot be deleted")
            LOG.error(response.json())
        return

    def delete_resource(self, resource_id: str, metadata_id: str, include_private=True):
        """Delete from the datalake the resource with id=resource_id
        :param resource_id: string containing the resource_id
        """
        self.set_access_token()

        response = requests.post(
            settings.data_lake_resource_delete(),
            json={"id": resource_id},
            headers=settings.data_lake_headers(self.access_token),
        )
        if response.status_code // 100 == 2:
            resp_as_dict = response.json()
            LOG.info(f"Data Lake resource with id {resource_id} deleted: {resp_as_dict}")

            if self.is_dataset_empty(metadata_id):
                self.delete_dataset(metadata_id)

        else:
            LOG.error(f"Data Lake resource with id {resource_id} cannot be deleted")
            LOG.error(response.json())

        return True
        return True
