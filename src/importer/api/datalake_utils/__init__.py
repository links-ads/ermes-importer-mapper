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
    """Gets the layer metadata given the metadata_id.

    :param project_name: project_name of the layer
    :type porject_name: str

    :param metadata_id: metadata_id of the layer. It is returned by the API /layers
    :type metadata_id: str
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
