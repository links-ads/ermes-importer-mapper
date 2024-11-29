from datetime import datetime
from typing import Optional

from geoalchemy2.elements import WKBElement
from geoalchemy2.shape import to_shape
from pydantic import BaseModel, validator


class ORMModel(BaseModel):
    """Generic pydantic model in ORM mode by default, to deal with 90% of the use cases."""

    class Config:
        orm_mode = True


class MessageSchema(BaseModel):
    geometry: dict
    datatype_id: int
    start_date: datetime
    end_date: datetime
    creation_date: Optional[datetime]
    type: str
    url: Optional[str]
    id: str
    name: str
    metadata_id: Optional[str]
    destinatary_organization: Optional[str]
    request_code: Optional[str]


class DownloadedDataSchema(BaseModel):
    workspace: str
    datatype_id: str
    store_name: Optional[str]
    start: datetime
    end: datetime
    creation_date: Optional[datetime]
    resource_id: str
    resource_name: str
    metadata_id: str
    bbox: dict
    tmp_path: str
    destinatary_organization: Optional[str]
    request_code: str
    mosaic: bool
    additional_attributes: Optional[dict]


def ewkb_to_wkt(geom: WKBElement):
    """
    Converts a geometry formated as WKBE to WKT
    in order to parse it into pydantic Model

    Args:
        geom (WKBElement): A geometry from GeoAlchemy query
    """
    return to_shape(geom).wkt


class GeoserverResourceSchema(ORMModel):
    datatype_id: str  # used for all kind of data
    workspace: str  # used for all kind of data
    store_name: str  # used for data stored in db
    layer_name: str  # used for all kind of data. It is the table_name of data stored on db
    layer_title: Optional[str]  # used for all kind of data
    storage_location: Optional[str]  # used for data stored in a directory
    expire_on: Optional[datetime]  # used for all kind of data
    start: datetime  # used for all kind of data
    end: datetime  # used for all kind of data
    creation_date: Optional[datetime]  # used for all kind of data
    resource_id: str  # used for all kind of data
    metadata_id: str  # used for all kind of data
    bbox: str  # used for all kind of data,
    dest_org: Optional[str]  # used for all kind of data
    request_code: Optional[str]  # used for all kind of data,
    timestamps: Optional[str]  # used for all kind of data
    mosaic: bool  # Storage location is a directory - import as ImageMosaic

    @validator("bbox", pre=True, allow_reuse=True, whole=True, always=True)
    def correct_geom_format(cls, v):

        if not isinstance(v, WKBElement):
            raise ValueError(f"must be a valid WKBE element. Is a {type(v)}")
        return ewkb_to_wkt(v)


class LayerSettingsSchema(ORMModel):
    project: str
    master_datatype_id: str  # used for all kind of data
    datatype_id: str  # used for all kind of data
    var_name: str  # used for all kind of data
    style: str
    delete_after_days: int
    delete_after_count: int
    format: str
    time_dimension: bool
    time_attribute: str
    parameters: str
