import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from importer.api.dashboard import domain as dashboard_domain
from importer.database.extensions import db_webserver
from importer.database.schemas import GeoserverResourceSchema
from importer.driver.datalake_driver import DataLakeDriver

LOG = logging.getLogger(__name__)
router = APIRouter()


@router.get("/metadata", status_code=200)
def get_metadata(organization: str, metadata_id: str):
    """
    Retrieve the metadata of a layer based on the given `metadata_id`.

    ### Parameters:
    - **organization**:
        - The name of the geodatalake organization (project) of the layer.
        - **Type**: `str`
    - **metadata_id**:
        - The ID of the metadata associated with the layer. This is typically returned by the `/layers` API.
        - **Type**: `str`
    ### Returns:
    - The metadata for the specified layer.
    - **Type**: `json`
    """
    driver = DataLakeDriver()
    metadata = driver.get_metadata(organization, metadata_id)
    if not metadata:
        raise HTTPException(status_code=404, detail="metadata id not found")
    return metadata


@router.delete("/delete_layer", response_model=List[GeoserverResourceSchema], status_code=200)
def delete_layers(
    organization: str,
    datatype_ids: Optional[List[str]] = Query(None),
    destinatary_organizations: Optional[List[str]] = Query(None),
    request_codes: Optional[List[str]] = Query(None),
    layer_name: Optional[str] = Query(None),
    resource_id: Optional[str] = Query(None),
    db: Session = Depends(db_webserver),
):
    """
    Delete resources associated with layers from the data lake, based on provided filters.

    ### Parameters:
    - **organization**: 
        - The name of the organization that owns the resources.
        - **Type**: `str`
    - **datatype_ids**: 
        - A list of `datatype_id` values to filter the resources by.
        - **Type**: `Optional[List[str]]`
        - **Default**: `Query(None)`
    - **destinatary_organizations**:
        - A list of destinatary organizations to filter by.
        - **Type**: `Optional[List[str]]`
        - **Default**: `Query(None)`
    - **request_codes**: 
        - A list of request codes associated with the map requests.
        - **Type**: `Optional[List[str]]`
        - **Default**: `Query(None)`
    - **layer_name**: 
        - The name of the layer whose associated resources are to be deleted.
        - **Type**: `Optional[str]`
        - **Default**: `Query(None)`
    - **resource_id**: 
        - The ID of the resource to be deleted.
        - **Type**: `Optional[str]`
        - **Default**: `Query(None)`
    - **db**: 
        - The database session instance for interacting with the data lake.
        - **Type**: `Session`
        - **Default**: `Depends(db_webserver)`

    ### Returns:
    - A list of resources that have been deleted.
    - **Type**: `List[GeoserverResourceSchema]`
    """
    driver = DataLakeDriver()
    deleted_resources_list = []
    pars = datatype_ids or request_codes or layer_name or resource_id
    LOG.info(f"empty pars: {pars}")

    if pars:
        resources = dashboard_domain.get_resources(
            db,
            workspace=organization,
            datatype_ids=datatype_ids,
            resource_id=resource_id,
            layer_name=layer_name,
            destinatary_organizations=destinatary_organizations,
            request_codes=request_codes,
        )

        for resource in resources:
            LOG.info(f"resource to delete: {resource.resource_id}")
            try:
                driver.delete_resource(resource.workspace, resource.resource_id, resource.metadata_id)
                deleted_resources_list.append(resource)
                LOG.info(f"resource deleted: {resource.resource_id}")
            except Exception as e:
                LOG.error(e)
                continue
    return deleted_resources_list
