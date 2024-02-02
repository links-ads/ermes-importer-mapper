import logging
from sqlalchemy.sql.sqltypes import DateTime
from importer.database.models import GeoserverResource
from typing import List, Optional
from sqlalchemy.orm import Session
import shapely.geometry
from shapely.geometry.multipolygon import MultiPolygon
from geoalchemy2 import WKTElement

LOG = logging.getLogger(__name__)


def get_resources(
    session: Session,
    datatype_ids: Optional[List[str]] = None,
    resource_id: Optional[str] = None,
    layer_name: Optional[str] = None,
    point: Optional[str] = None,
    bbox: Optional[str] = None,
    start: Optional[DateTime] = None,
    end: Optional[DateTime] = None,
    request_codes: Optional[List[str]] = None,
    include_deleted: Optional[bool] = False,
    exclude_valued_request_code: Optional[bool] = False,
    order_by: Optional[str] = None,
) -> List[GeoserverResource]:

    statement = session.query(GeoserverResource)

    if not include_deleted:
        statement = statement.filter(GeoserverResource.deleted_at.is_(None))
    if datatype_ids:
        statement = statement.filter(GeoserverResource.datatype_id.in_(datatype_ids))
    if resource_id:
        statement = statement.filter(GeoserverResource.resource_id == resource_id)
    if layer_name:
        statement = statement.filter(GeoserverResource.layer_name == layer_name)
    if request_codes:
        statement = statement.filter(GeoserverResource.request_code.in_(request_codes))
    if exclude_valued_request_code:
        statement = statement.filter(GeoserverResource.request_code.is_(None))
    if point:
        bbox = get_bbox_from_point(point)
    if bbox:
        LOG.info(bbox)
        polygon = shapely.geometry.box(*[float(coord) for coord in bbox.split(",")], ccw=True)
        multipolygon = MultiPolygon([polygon])
        # statement = statement.filter(GeoserverResource.bbox.ST_Intersects(WKTElement(multipolygon.wkt, srid=4326)))
        statement = statement.filter(GeoserverResource.bbox.ST_Intersects(WKTElement(multipolygon.wkt)))
    if start:
        statement = statement.filter(GeoserverResource.end >= start)
    if end:
        statement = statement.filter(end >= GeoserverResource.start)
    if order_by:
        statement = statement.order_by(order_by)

    return statement.all()


def get_bbox_from_point(point: str):
    x, y = point.x, point.y
    bbox = f"{x},{y},{round(x+.001, 3)},{round(y+.001, 3)}"
    return bbox
