import logging
from datetime import datetime
from typing import Optional
from typing import List
from fastapi import HTTPException
from pydantic import BaseModel, ValidationError, validator
from shapely import wkt

LOG = logging.getLogger(__name__)


class TimeSeriesSchema(BaseModel):
    """
    Schema that defines the input for the time series GET requests.
    """

    datatype_id: str
    point: str
    attribute: str
    start: datetime = datetime(1794, 1, 1, 0, 0, 0)
    end: datetime = datetime.utcnow()
    geom_col: str = "geometry"
    date_start_col: str = "date_start"
    date_end_col: str = "date_end"
    creation_date_col: str = "computation_time"

    @validator("point")
    def check_process_count(cls, p):
        try:
            point = wkt.loads(p.point)
            if point.type != "Point":
                raise Exception
        except Exception:
            raise ValidationError("Invalid format: it should be POINT(X Y)")
        return p


class TimeSeriesSchema_v2(BaseModel):
    """
    Schema that defines the input for the time series GET requests.
    """

    datatype_id: str
    workspace: str
    request_code: Optional[str]
    layer_name: Optional[str] = None
    point: str
    start: Optional[datetime] = datetime(1794, 1, 1, 0, 0, 0)
    end: Optional[datetime] = datetime.utcnow().isoformat()
    crs: str
    attribute: Optional[str]
    geom_col: str = "geometry"
    date_start_col: str = "date_start"
    date_end_col: str = "date_end"
    creation_date_col: str = "computation_time"

    @validator("point")
    def check_process_count(cls, p, values):
        try:
            p = wkt.loads(p)
            if p.geom_type != "Point":
                raise Exception
        except Exception:
            raise HTTPException(status_code=422, detail="Invalid format: it should be POINT(X Y)")
        return p

    @validator("crs")
    def check_crs(cls, crs):
        try:
            epsg, number = crs.split(":")
            if epsg != "EPSG" or not number.isnumeric():
                raise ValueError
        except ValueError:
            raise HTTPException(status_code=422, detail="Check the CRS. It should be like 'EPSG:4326'")
        return crs

    @validator("start")
    def check_time_range(cls, start, values):
        LOG.info(values)
        # if (values['stop'] - start).total_seconds() < 0:
        #     raise ValidationError('stop date must be after the start date')
        return start
