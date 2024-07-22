import errno
import io
import logging
import os
import re
import zipfile
from typing import List

from importer.database.schemas import DownloadedDataSchema, MessageSchema
from importer.driver.datalake_driver import DataLakeDriver

LOG = logging.getLogger(__name__)


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

    def download_data(self, project_name, message_schema: MessageSchema) -> List[DownloadedDataSchema]:
        """Retrieve data contained in the received message from their urls.
        Returns a list containing the temporary folder where files were saved
        :param dict message: message coming from message bus, containing the
                             urls of the resources to download
        """
        data_list = []

        r, url = self.driver.get(project_name, message_schema.id, message_schema.url)  # use driver to download data
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
                workspace=project_name,
                datatype_id=message_schema.datatype_id,
                store_name=store_name,
                start=message_schema.start_date,
                end=message_schema.end_date,
                creation_date=message_schema.creation_date,
                resource_id=message_schema.id,
                resource_name=message_schema.name,
                metadata_id=message_schema.metadata_id,
                bbox=message_schema.geometry,
                destinatary_organization=message_schema.destinatary_organization,
                request_code=message_schema.request_code,
                tmp_path=tmp_path,
                mosaic=ismosaic,
            )
            data_list.append(data)
        LOG.info(f'{len(data_list)} resource{"s" if len(data_list) > 1 else ""} downloaded')
        return data_list
