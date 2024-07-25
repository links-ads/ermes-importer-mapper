import asyncio
import os
from datetime import datetime
from typing import List, Optional

import dateutil.parser as dp
import pandas as pd
import pytz
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from importer.__main__ import LOG
from importer.api.dashboard import domain
from importer.api.dashboard.dto import TimeSeriesSchema_v2
from importer.database.extensions import db_webserver
from importer.database.models import GeoserverResource
from importer.database.schemas import GeoserverResourceSchema
from importer.driver.geoserver_driver import GeoserverDriver
from importer.driver.postgis_driver import PostGISDriver
from importer.manager.data_storage_manager import DataStorageManager
from importer.manager.geoserver_manager import GeoserverManager
from importer.settings.instance import settings
from importer.util.datetimeutils import isoformat_Z, set_utc_default_tz

router = APIRouter()


@router.get("/resources", response_model=List[GeoserverResourceSchema], status_code=200)
def get_resources(
    workspace: str,
    datatype_ids: Optional[List[str]] = Query(None),
    resource_id: Optional[str] = Query(None),
    include_deleted: Optional[bool] = False,
    db: Session = Depends(db_webserver),
):
    """Gets stored resources following the given optional criteria.

    :param db: DB session instance, defaults to Depends(db_webserver)
    :type db: Session, optional
    :return: list of resource models to be serialized
    :rtype: List[GeoserverResourceSchema]
    """
    resources = domain.get_resources(
        db, workspace, datatype_ids=datatype_ids, resource_id=resource_id, include_deleted=include_deleted
    )
    return resources


def __get_filtered_ts(timeseries, start, end):
    # return list of timestamps between start and end.
    # In case of empty list, it includes the timestamp precedent of the start
    timestamps = []
    # format so to use lexicographic ordering
    start = isoformat_Z(set_utc_default_tz(start))
    end = isoformat_Z(set_utc_default_tz(end))
    timeseries_list = timeseries.split(";")

    # handle exception
    if len(timeseries_list) == 0:
        return timestamps

    first_ts = timeseries_list[0]
    for ts in timeseries_list:
        if len(ts) > 0 and (ts > first_ts) and start and (ts < start):
            first_ts = ts
        if len(ts) > 0 and (start is None or ts >= start) and (end is None or ts <= end):
            timestamps.append(ts)

    # In case of empty list, it includes the timestamp precedent of the start
    if len(timestamps) == 0:
        timestamps.append(first_ts)

    return timestamps


@router.get("/layers", status_code=200)
def get_layers(
    workspace: str,
    datatype_ids: Optional[List[str]] = Query(None),
    bbox: Optional[str] = Query(None),
    start: Optional[datetime] = Query(None),
    end: Optional[datetime] = Query(None),
    destinatary_organizations: Optional[List[str]] = Query(None),
    request_codes: Optional[List[str]] = Query(None),
    include_map_requests: Optional[bool] = Query(True),
    db: Session = Depends(db_webserver),
):
    """Gets the list of published layers given optional criteria.

    :param datatype_ids: list of datatype_id to filter by, defaults to Query(None)
    :type datatype_ids: Optional[List[str]], optional
    :param bbox: bounding box string in the form "bottomleft-x,bottomleft-y,topright-x,topright-y",
    defaults to Query(None)
    :type bbox: Optional[str], optional
    :param start: filter resources with start_date >= start, start in the form 'YYYY-MM-DD HH:MM:SS',
    defaults to Query(None)
    :type start: Optional[datetime], optional
    :param end: filter resources with end_date <= end, end in the form 'YYYY-MM-DD HH:MM:SS', defaults to Query(None)
    :type end: Optional[datetime], optional
    :param dest_organization: filter resources with destinatary_organization specified
    :type dest_organization: Optional[str], optional
    :type request_codes: Optional[List[str]], optional
    :param db: DB session instance, defaults to Depends(db_webserver)
    :type db: Session, optional
    :return: list of layers grouped by datatype id
    :rtype: List[Dict[str,Dict[str,object]]]
    """
    resources = domain.get_resources(
        db,
        workspace=workspace,
        datatype_ids=datatype_ids,
        bbox=bbox,
        start=start,
        end=end,
        destinatary_organizations=destinatary_organizations,
        request_codes=request_codes,
        exclude_valued_request_code=(not include_map_requests),
        order_by=GeoserverResource.created_at,
    )

    datatype_groups = {}
    for resource in resources:
        datatype_groups.setdefault(resource.datatype_id, []).append(resource)
    LOG.info(f"Found {len(resources)} layers")
    result = {
        "items": [
            {
                "datatype_id": key,
                "details": (
                    {
                        "name": f"{resource.workspace}:{resource.layer_name}",
                        "timestamps": __get_filtered_ts(resource.timestamps, start, end),
                        "created_at": resource.created_at.isoformat(timespec="seconds"),
                        "destinatary_organization": resource.dest_org,
                        "request_code": resource.request_code,
                        "metadata_id": resource.metadata_id,
                    }
                    for resource in group
                ),
            }
            for key, group in datatype_groups.items()
        ]
    }
    LOG.info("Response ready")
    return result


@router.get("/timeseries", status_code=200)
def get_timeseries(params: TimeSeriesSchema_v2 = Depends(), db: Session = Depends(db_webserver)):
    """Retrieves the time series of the requested attribute for layers denoted by the specified datatype_id,
    at the "point" position

    :param datatype_id: datatype_id of the layers to retrieve the attribute time series from
    :type datatype_id: str

    :param request_code: request code of the layers to retrieve the attribute time series from
    :type request_code: str

    :param point: point string in the WKT form PONIT(x y)
    :type point: str

    :param start: start date in the form 'YYYY-MM-DD HH:MM:SS' filter resources with start_date >= start,
    defaults to Query(None)
    :type start: Optional[datetime], optional

    :param end: end date in the form 'YYYY-MM-DD HH:MM:SS' filter resources with end_date <= end,
    defaults to Query(None)
    :type end: Optional[datetime], optional

    :param crs: coordinate reference system. For example: 'EPSG:4326'
    :type crs: str

    :param attribute: name of the column containing the requested attribute
    :type attribute: Optional[str]

    :param geom_col: name of the db table column containing the geometry
    :type geom_col: Optional[str]

    :param date_start_col: name of the db table column containing the activation start date
    :type date_start_col: Optional[str]

    :param date_end_col: name of the db table column containing the activation end date
    :type date_end_col: Optional[str]

    :param creation_date_col: name of the column to use when choosing between multiple table rows
    with the same start_date.
                              Pick always the row with the most recent creation_date_col
    :type creation_date_col: Optional[str]

    :param db: DB session instance, defaults to Depends(db_webserver)
    :type db: Session, optional

    :return: time series of the attribute values at "point" location
    :rtype: json

    Example: I have many GeoJSON files that form a time series saved on the PostGIS db,
    each containing polygons with certain values over a specified area.
    I want to get the series of the "temperature" value of the point 15.18,41.68 from date 2020-02-04 00:00:00
    to date 2020-02-11 23:59:59.
    Supposing that the GeoJSON files have their geometries saved in the "geometry" column, their start reference date
    saved in the "date_start" column and
    their end reference date in the "date_end" column, specifying all these parameters returns me a dataframe
    with all the values of the "temperature" variable
    contained in the GeoJSON files for the requested time period, at the specified point location.
    The "creation_date_col" is used when multiple files span the
    same time (to be more precise, have the same "date_start"), only the most recent is returned.
    """

    data_storage_manager = DataStorageManager()
    layer_settings = data_storage_manager.get_layer_settings(
        db, project=params.workspace, datatype_id=params.datatype_id
    )

    if not layer_settings:
        raise HTTPException(status_code=404, detail="Settings for those parameters not found in DB")

    format_ = layer_settings.format.lower()
    if params.request_code:
        resources = domain.get_resources(
            db,
            workspace=params.workspace,
            datatype_ids=[params.datatype_id],
            destinatary_organizations=[params.destinatary_organization],
            request_codes=[params.request_code],
            layer_name=params.layer_name,
            start=params.start,
            end=params.end,
            order_by="start",
        )
    else:
        LOG.info("no request code")
        resources = domain.get_resources(
            db,
            workspace=params.workspace,
            datatype_ids=[params.datatype_id],
            destinatary_organizations=[params.destinatary_organization],
            layer_name=params.layer_name,
            start=params.start,
            end=params.end,
        )

    layer_names = [resource.layer_name for resource in resources]
    timestamps_ = [resource.timestamps for resource in resources]

    # filter out timestamps inside the range specified in the request
    timestamps = []
    for ts_ in timestamps_:
        ts_list = ts_.split(";")
        start = params.start
        if start:
            if start.tzinfo is None:
                start = pytz.utc.localize(start)
            ts_list = list(filter(lambda t: dp.parse(t) >= start, ts_list))
        end = params.end
        if end:
            if end.tzinfo is None:
                end = pytz.utc.localize(end)
            ts_list = list(filter(lambda t: dp.parse(t) <= end, ts_list))
        timestamps.append(ts_list)

    if len(resources) == 0:
        raise HTTPException(status_code=404, detail="No resources found")

    if len(resources) > 1000:
        raise HTTPException(
            status_code=429, detail="Your request includes more than 1000 layers. Try a shorter datetime range"
        )

    LOG.info(f"format: {format_}")
    LOG.info(f"layer_names: {layer_names}")
    LOG.info(f"timestamps: {timestamps}")
    # netcdf layers -> leverage Geoserver WMS gettimeseries
    if format_ == "netcdf":
        if len(resources) > 100:
            raise HTTPException(
                status_code=429, detail="Your request includes more than 100 layers. Try a shorter datetime range"
            )
        driver = GeoserverDriver()
        try:
            timeseries = asyncio.run(
                driver.get_timeseries_from_netcdf(
                    workspace=params.workspace,
                    layers=layer_names,
                    bbox=domain.get_bbox_from_point(params.point),
                    crs=params.crs,
                    timestamps=timestamps,
                )
            )
        except Exception as e:
            LOG.error(f"Error: {e}")
            timeseries = pd.DataFrame()
            # raise HTTPException(status_code=404, detail=f'Data not found, Check the parameters of the request.')

    # geojson -> use Geoserver WMS getfeatureinfo
    elif format_ in ["geojson", "tif", "tiff", "geotiff"]:
        driver = GeoserverDriver()
        try:
            timeseries = asyncio.run(
                driver.get_timeseries_from_featureinfo(
                    workspace=params.workspace,
                    resources=resources,
                    bbox=domain.get_bbox_from_point(params.point),
                    crs=params.crs,
                    timestamps=timestamps,
                )
            )
        except Exception as e:
            LOG.error(f"Error: {e}")
            timeseries = pd.DataFrame()
            # raise HTTPException(status_code=404, detail='Data not found, check the parameters of the request')

    # shapefile -> query the tables in DB
    elif format_ in ["shapefile"]:
        driver = PostGISDriver()
        try:
            timeseries = pd.DataFrame(
                driver.get_table_value(
                    table_names=layer_names,
                    column=params.attribute,
                    point=params.point,
                    geom_col=params.geom_col,
                    date_start_col=params.date_start_col,
                    date_end_col=params.date_end_col,
                    creation_date_col=params.creation_date_col,
                )
            ).drop(columns=[params.geom_col])
        except Exception as e:
            LOG.error(f"Error: {e}")
            timeseries = pd.DataFrame()
            # raise HTTPException(status_code=404, detail='Data not found, check the parameters of the request')

    LOG.info(f"data: {timeseries}")

    # dataframe to json response
    timeseries = timeseries.round(2).fillna("")
    data = []
    if timeseries.empty:
        LOG.info("Empty timeseries!")
    else:
        for col in timeseries.columns:
            LOG.info(timeseries.index)
            f_dict = {"var_name": col}
            f_dict["values"] = [{"datetime": dt, "value": v} for dt, v in zip(timeseries.index, timeseries[col])]
            LOG.info(f_dict)
            data.append(f_dict)

    return data


# TODO: add workspace parameter
# @router.get("/check_layers", response_model=List[GeoserverResourceSchema], status_code=200)
# def get_check_layers(delete_missings: Optional[bool] = False, db: Session = Depends(db_webserver)):
#     """Check if all the files are actually available,

#     :param delete_missings: delete all the layers not available
#     :type delete_missings: boolean
#     :param db: DB session instance, defaults to Depends(db_webserver)
#     :type db: Session, optional
#     :return: list of resource models to be serialized
#     :rtype: List[GeoserverResourceSchema]
#     """
#     geoserver_manager = GeoserverManager()
#     data_storage_manager = DataStorageManager()
#     resources = domain.get_resources(db, include_deleted=False)
#     missing_layers = []
#     for res in resources:
#         if (res.storage_location) and (not os.path.exists(res.storage_location)):
#             missing_layers.append(res)
#     LOG.info(f"Missing layers: {missing_layers}")
#     if delete_missings:
#         LOG.info("deleting layers...")
#         reslayercount = data_storage_manager.countlayers_perresource(session=db, resources=missing_layers)
#         geoserver_manager.delete(resources=missing_layers, resourcelayercount=reslayercount)
#     return missing_layers
