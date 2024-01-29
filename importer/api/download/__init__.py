import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.responses import FileResponse
from importer.api.download import domain
from importer.database.extensions import db_webserver
from importer.security import api_key_auth
from settings.instance import settings
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

LOG = logging.getLogger(__name__)
router = APIRouter()


@router.get("/resource_path", status_code=200, dependencies=[Security(api_key_auth)])
def get_resource_path(
    layer_name: str = Query(None), resource_id: str = Query(None), db: Session = Depends(db_webserver)
):
    """Return the temporary filename containing the resource

    :param layer_name: name of the layer. It is returned by the API /layers
    :type layer_name: str

    :param resource_id: resource_id of the layer. It is returned by the API /layers
    :type resource_id: str

    :return: temporary filepath
    :rtype: text/json
    """
    assert layer_name or resource_id, HTTPException(status_code=422, detail="Specify at least one parameter")

    resources = domain.get_resources(db, resource_id=resource_id, layer_name=layer_name)
    if len(resources) == 0:
        raise HTTPException(status_code=404, detail="Resource not found")

    resource = resources[0]
    filepath_origin = resource.storage_location
    if not filepath_origin:
        temp_filename = domain.get_resource_from_dl(resource.resource_id)
    else:
        temp_filename = domain.prepare_resource(filepath_origin)

    if not temp_filename:
        raise HTTPException(status_code=404, detail="Resource not found")

    return {"filename": temp_filename}


@router.get("/download", status_code=200, response_class=FileResponse)
def download_resource(filename: str):
    """Gets the resource file given the temporal path returned by API GET resource_path.

    :param filepath: filepath of the resource. This is just a temporary path
    :type metadata_id: str

    :return: Resource binary file
    :rtype: application/octet-stream
    """

    def cleanup():
        # delete current file
        LOG.info(f"Remove temp file {filepath}")
        os.remove(filepath)

        # delete older files
        LOG.info("Purging temp old files")
        path = os.path.dirname(filepath)
        now = time.time()

        for filename in os.listdir(path):
            filestamp = os.stat(os.path.join(path, filename)).st_mtime
            filecompare = now - 86400  # 24 hours
            if filestamp < filecompare:
                try:
                    os.remove(os.path.join(path, filename))
                except IsADirectoryError:
                    LOG.info(f"{filename} is a directory")
                    pass

    if not filename:
        raise HTTPException(status_code=404, detail="Download not available")
    filepath = os.path.join(settings.get_temp_folder(), filename)
    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=404, detail="Download not available, use GET resource_path to get the filename"
        )
    headers = {}
    headers["Content-Disposition"] = f"attachment; filename={filename}"
    return FileResponse(filepath, headers=headers, background=BackgroundTask(cleanup))
