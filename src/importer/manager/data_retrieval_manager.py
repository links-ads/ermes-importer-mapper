from importer.database.schemas import DownloadedDataSchema, MessageSchema
from typing import List
from importer.driver.datalake_driver import DataLakeDriver
import io
import os
import zipfile
import logging
import errno
import re

LOG = logging.getLogger(__name__)
# 'https://datalake-test.shelter-project.cloud/dataset/51a6abe4-8f3c-441a-9efe-f9c62bd47720/resource/9630c901-dc87-42c7-a894-a104aa18c77b/download/58c07c0c-ba67-42c0-bc7c-ca47291c275c5c32002_links_burned_area_delineation_0_20190718t000000_201.tiff'
# 'https://datalake-test.shelter-project.cloud/dataset/ef0d301f-3b41-446c-91b8-aa686c94f751/resource/de2c5c20-5299-48c0-82ec-5e80eff882d1/download/emsr035_01sisak_delineation_detail01_v2_vector.zip'


def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def safe_open(path, mode):
    """Open "path" for writing, creating any parent directories as needed."""
    mkdir_p(os.path.dirname(path))
    return open(path, mode)


def sanitize(name: str):
    regex = re.compile("[^a-zA-Z0-9_-]")
    # First parameter is the replacement, second parameter is your input string
    return regex.sub("", name)


class DataRetrievalManager:
    def __init__(self):
        self.driver = DataLakeDriver()

    def download_data(self, message_schema: MessageSchema) -> List[DownloadedDataSchema]:
        """Retrieve data contained in the received message from their urls.
        Returns a list containing the temporary folder where files were saved
        :param dict message: message coming from message bus, containing the
                             urls of the resources to download
        """
        data_list = []

        r, url = self.driver.get(message_schema.id, message_schema.url)  # use driver to download data
        filename = url.split("/")[-1]
        extension = filename.split(".")[-1]
        tmp_path = os.path.join("temp", message_schema.id)  # create a temporary folder to save files to
        ismosaic = False
        isdbstored = False
        if r.status_code == 200:
            content = io.BytesIO(r.content)
            if extension == "zip" or extension == "mapping":
                try:
                    z = zipfile.ZipFile(content)
                    z.extractall(path=tmp_path)  # extract all files to folder
                    z.close()

                    ismosaic = (extension == "mapping") or any(
                        [(f.endswith(".tif") or f.endswith(".tiff")) for f in os.listdir(tmp_path)]
                    )
                    isdbstored = not ismosaic
                except zipfile.BadZipFile as e:
                    LOG.error(r.content)
                    raise e
            elif extension in ["tif", "tiff", "json", "geojson", "kml", "nc", "ncml"]:
                isdbstored = extension in ["json", "geojson", "kml"]
                with safe_open(os.path.join(tmp_path, filename), "wb") as f:  # save the single file to folder
                    for chunk in r:
                        f.write(chunk)
            else:
                LOG.error(f"File with extension {extension} not supported")
            store_name = "postgis_db" if isdbstored else None
            data = DownloadedDataSchema(
                datatype_id=message_schema.datatype_id,
                store_name=store_name,
                start=message_schema.start_date,
                end=message_schema.end_date,
                creation_date=message_schema.creation_date,
                resource_id=message_schema.id,
                metadata_id=message_schema.metadata_id,
                bbox=message_schema.geometry,
                request_code=message_schema.request_code,
                tmp_path=tmp_path,
                mosaic=ismosaic,
            )
            data_list.append(data)
        LOG.info(f'{len(data_list)} resource{"s" if len(data_list) > 1 else ""} downloaded')
        return data_list
