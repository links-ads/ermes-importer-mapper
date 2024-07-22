from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import Boolean, Column, Integer, String, Text

from importer.database import APIModel, TimezoneDateTime


class GeoserverResource(APIModel):
    __tablename__ = "geoserver_resource"
    id = Column(Integer, primary_key=True)
    datatype_id = Column(String(64), nullable=False)
    workspace = Column(String(64), nullable=False)
    store_name = Column(String(64), nullable=False)  # "postgis_db" or layer_name
    layer_name = Column(String(128), nullable=False)
    storage_location = Column(String(256), nullable=True)
    created_at = Column(TimezoneDateTime, default=datetime.utcnow, nullable=False)
    deleted_at = Column(TimezoneDateTime, nullable=True)
    expire_on = Column(TimezoneDateTime, nullable=True)
    start = Column(TimezoneDateTime, nullable=False)
    end = Column(TimezoneDateTime, nullable=False)
    resource_id = Column(String(128), nullable=False)
    metadata_id = Column(String(128), nullable=True)
    bbox = Column(Geometry(srid=4326, geometry_type="MULTIPOLYGON"), nullable=False)
    dest_org = Column(String(64), nullable=True)
    request_code = Column(String(128), nullable=True)
    timestamps = Column(Text, nullable=False)
    mosaic = Column(Boolean, server_default="0")


class LayerSettings(APIModel):
    __tablename__ = "layer_settings"
    id = Column(Integer, primary_key=True)
    project = Column(String(64), nullable=False)
    master_datatype_id = Column(String(64), nullable=True, server_default=None)
    datatype_id = Column(String(64), nullable=False)
    var_name = Column(String(64), nullable=True, server_default=None)
    style = Column(String(64), nullable=True)
    delete_after_days = Column(Integer, nullable=True)
    delete_after_count = Column(Integer, nullable=True)
    format = Column(String(64), nullable=False)
    time_dimension = Column(Boolean, server_default="0")
    time_attribute = Column(String(64), server_default=None, nullable=True)
    parameters = Column(Text, server_default=None, nullable=True)
