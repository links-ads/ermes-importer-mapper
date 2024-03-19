import os
import shutil
import time
import uuid
from typing import List, Optional

from sqlalchemy.orm import Session

from importer.database.models import GeoserverResource
from importer.driver.datalake_driver import DataLakeDriver
from importer.settings.instance import settings


def get_resources(
    session: Session,
    workspace: str,
    datatype_ids: Optional[List[str]] = None,
    resource_id: Optional[str] = None,
    layer_name: Optional[str] = None,
    order_by: Optional[str] = None,
) -> List[GeoserverResource]:
    statement = session.query(GeoserverResource)
    statement = statement.filter(GeoserverResource.workspace == workspace)
    if datatype_ids:
        statement = statement.filter(GeoserverResource.datatype_id.in_(datatype_ids))
    if resource_id:
        statement = statement.filter(GeoserverResource.resource_id == resource_id)
    if layer_name:
        statement = statement.filter(GeoserverResource.layer_name == layer_name)
    if order_by:
        statement = statement.order_by(order_by)

    return statement.all()


def get_temporary_name(filepath: str):
    # the first 6 chars contain the datatype_id and therefore are kept,
    # the remaining filename is random generated + current time
    filename = os.path.basename(os.path.normpath(filepath))
    return f"{filename[:6]}{str(uuid.uuid4())[:8]}_{int(time.time())}"


def prepare_resource(filepath: str):
    temp_folder = settings.get_temp_folder()

    if not os.path.exists(filepath):
        return None
    if not os.path.exists(temp_folder):
        os.mkdir(temp_folder)

    temp_filename = get_temporary_name(filepath)  # generate random filename w/o extension
    dest_filepath = os.path.join(temp_folder, temp_filename)  # temp filepath w/o extension

    # if folder, create the zip file
    if os.path.isdir(filepath):
        shutil.make_archive(dest_filepath, "zip", filepath)
        file_extension = ".zip"

    # otherwise copy the file with the temporary name in the temp folder
    else:
        _, file_extension = os.path.splitext(filepath)  # get extension
        dest_filepath = f"{dest_filepath}{file_extension}"
        shutil.copy(filepath, dest_filepath)  # copy file in temp_folder

    return f"{temp_filename}{file_extension}"


def get_resource_from_dl(organization: str, resource_id: str):
    temp_folder = settings.get_temp_folder()
    driver = DataLakeDriver()

    f_, filename = driver.download_resource(organization=organization, resource_id=resource_id)
    _, file_extension = os.path.splitext(filename)
    temp_filename = f"{get_temporary_name(filename)}{file_extension}"  # generate random filename w/ extension
    dest_filepath = os.path.join(temp_folder, temp_filename)  # temp filepath w/ extension

    with open(dest_filepath, "wb") as outfile:
        # Copy the BytesIO stream to the output file
        outfile.write(f_.getbuffer())
    return temp_filename
    return temp_filename
