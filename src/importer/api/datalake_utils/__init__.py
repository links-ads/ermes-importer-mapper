import logging
from importer.driver.datalake_driver import DataLakeDriver
from importer.database.schemas import GeoserverResourceSchema
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from importer.database.extensions import db_webserver
from importer.api.dashboard import domain as dashboard_domain

LOG = logging.getLogger(__name__)
router = APIRouter()


@router.get("/metadata", status_code=200)
def get_metadata(metadata_id: str):
    """Gets the layer metadata given the metadata_id.

    :param metadata_id: metadata_id of the layer. It is returned by the API /layers
    :type metadata_id: str
    """
    driver = DataLakeDriver()
    metadata = driver.get_metadata(metadata_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="metadata id not found")
    return metadata


# @router.get("/download", status_code=200)
# def download_resource(layer_name: Optional[str] = Query(None),
#                       resource_id: Optional[str] = Query(None),
#                       db: Session = Depends(db_webserver)):
#     """Gets the resource file given the resource_id or layer_name.

#     :param resource_id: resource_id of the resource. It is returned by the API /layers
#     :type metadata_id: str

#     :param layer_name: name of the layer. It is returned by the API /layers
#     :type metadata_id: str
#     """
#     assert layer_name or resource_id, HTTPException(status_code=422, detail='Specify at least one parameter')

#     resources = dashboard_domain.get_resources(db, resource_id=resource_id, layer_name=layer_name)
#     if len(resources) == 0:
#         raise HTTPException(status_code = 404, detail='Resource not found')
#     resource_id = resources[0].resource_id
#     storage_location = resources[0].storage_location

#     driver = DataLakeDriver()
#     f_, filename = driver.download_resource(resource_id=resource_id)
#     LOG.info(f'filename:{filename}')
#     headers = {}
#     headers['Content-Disposition'] = f'attachment; filename={filename}'
#     return StreamingResponse(f_, media_type='application/octet-stream', headers=headers)
# return FileResponse(r, headers=headers, background=BackgroundTask(remove_file))


@router.delete("/delete_layer", response_model=List[GeoserverResourceSchema], status_code=200)
def delete_layers(
    datatype_ids: Optional[List[str]] = Query(None),
    request_codes: Optional[List[str]] = Query(None),
    layer_name: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    db: Session = Depends(db_webserver),
):
    """Delete the resource associated to the layer from the datalake

    :param datatype_ids: list of datatype_id to filter by, defaults to Query(None)
    :type datatype_ids: Optional[List[str]], optional
    :param request_codes: list of codes associated to the map requests
    :type request_codes: Optional[List[str]], optional
    :param layer_name: layer name of the resource
    :type layer_name: Optional[str], optional
    :param resource_id: id of the resource
    :type resource_id: Optional[str], optional
    :param db: DB session instance, defaults to Depends(db_webserver)
    :type db: Session, optional
    :return: list of resources deleted
    :rtype: List[GeoserverResourceSchema]
    """
    driver = DataLakeDriver()
    deleted_resources_list = []
    pars = datatype_ids or request_codes or layer_name or resource_id
    LOG.info(f"empty pars: {pars}")

    if pars:
        resources = dashboard_domain.get_resources(
            db, datatype_ids=datatype_ids, resource_id=resource_id, layer_name=layer_name, request_codes=request_codes
        )

        for resource in resources:
            LOG.info(f"resource to delete: {resource.resource_id}")
            try:
                driver.delete_resource(resource.resource_id, resource.metadata_id)
                deleted_resources_list.append(resource)
                LOG.info(f"resource deleted: {resource.resource_id}")
            except Exception as e:
                LOG.error(e)
                continue
    return deleted_resources_list
