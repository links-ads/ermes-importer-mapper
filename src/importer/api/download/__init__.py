import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Security
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from importer.api.download import domain
from importer.database.extensions import db_webserver
from importer.security import api_key_auth
from importer.settings.instance import settings

LOG = logging.getLogger(__name__)
router = APIRouter()


@router.get("/resource_path", status_code=200, dependencies=[Security(api_key_auth)])
def get_resource_path(
    workspace: str, layer_name: str = Query(None), resource_id: str = Query(None), db: Session = Depends(db_webserver)
):
    """
    Retrieve the temporary file path containing the resource.

    ### Parameters:
    - **workspace**:
        - The workspace that the resource belongs to.
        - **Type**: `str`
    - **layer_name**: 
        - The name of the layer. This is typically returned by the `/layers` API.
        - **Type**: `Optional[str]`
        - **Default**: `Query(None)`
    - **resource_id**: 
        - The ID of the resource associated with the layer. This is typically returned by the `/layers` API.
        - **Type**: `Optional[str]`
        - **Default**: `Query(None)`

    ### Returns:
    - The temporary file path for the resource.
    - **Type**: `text/json`
    """

    assert layer_name or resource_id, HTTPException(status_code=422, detail="Specify at least one parameter")

    resources = domain.get_resources(db, workspace=workspace, resource_id=resource_id, layer_name=layer_name)
    if len(resources) == 0:
        raise HTTPException(status_code=404, detail="Resource not found")

    resource = resources[0]
    filepath_origin = resource.storage_location
    if not filepath_origin:
        temp_filename = domain.get_resource_from_dl(resource.workspace, resource.resource_id)
    else:
        temp_filename = domain.prepare_resource(filepath_origin)

    if not temp_filename:
        raise HTTPException(status_code=404, detail="Resource not found")

    return {"filename": temp_filename}


@router.get("/download", status_code=200, response_class=FileResponse)
def download_resource(filename: str):
    """
    Retrieve the resource file using the temporary path returned by the `GET /resource_path` API.

    ### Parameters:
    - **filepath**: 
        - The temporary file path of the resource.
        - **Type**: `str`

    ### Returns:
    - The resource as a binary file.
    - **Type**: `application/octet-stream`
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
