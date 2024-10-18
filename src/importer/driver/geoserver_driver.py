import asyncio
import io
import logging
import os
from datetime import datetime
from itertools import chain
from typing import List

import aiohttp
import pandas as pd
import requests

from importer.driver.geoserverrest import GeoserverREST
from importer.dto.layer_publication_status import LayerPublicationStatus
from importer.manager.data_storage_manager import DataStorageManager
from importer.settings.instance import settings
from importer.util.datetimeutils import isoformat_Z, set_utc_default_tz

LOG = logging.getLogger(__name__)


class GeoserverDriver:
    def __init__(self):
        self.service_url = settings.get_service_url()
        self.geoserver = GeoserverREST(
            service_url=self.service_url,
            username=settings.geoserver_admin_user,
            password=settings.geoserver_admin_password,
        )
        self.dsm = DataStorageManager()

    def create_workspace(self, workspace: str):
        existing_workspace = self.geoserver.get_workspace(workspace)
        if not existing_workspace:
            LOG.info(f"Creating workspace {workspace}")
            result = self.geoserver.create_workspace(workspace=workspace)
            if result:
                LOG.info(result)

    def create_store(self, store_name: str, workspace: str):
        existing_datastore = self.geoserver.get_datastores(workspace=workspace)
        LOG.info(f'existing_datastore: {existing_datastore}')
        if existing_datastore["dataStores"] == "" or (
            store_name not in [dsitem["name"] for dsitem in existing_datastore["dataStores"]["dataStore"]]
        ):
            LOG.info(f"Creating store {store_name} for workspace {workspace}")
            result = self.geoserver.create_featurestore(
                workspace=workspace,
                store_name=store_name,
                db=settings.database_name,
                host=settings.database_host,
                pg_user=settings.database_user,
                pg_password=settings.database_pass,
            )
            if result:
                LOG.error(result)

    def publish_table(self, workspace: str, store_name: str, layer_name: str, layer_title: str, datatype: str, start_time: datetime):
        """
        Publishes a layer from a table in the geoserver.

        Args:
            workspace (str): The name of the workspace.
            store_name (str): The name of the store.
            layer_name (str): The name of the layer.
            datatype (str): The datatype of the layer.
            start_time (datetime): The start time.

        Returns:
            LayerPublicationStatus: An object representing the status of the layer publication.
        """
        LOG.info(f"Publishing layer {layer_name} from table")
        timestamps = [isoformat_Z(set_utc_default_tz(start_time))]
        try:
            self.geoserver.publish_featurestore(workspace=workspace, store_name=store_name, pg_table=layer_name)
            LOG.info(f"Layer {layer_name} successfully published from table!")
            err_status = None
            # if datatype has time dimension, update the featuretype with time dim
            if self.dsm.has_time_dimension(workspace, datatype):
                time_attribute = self.dsm.get_time_attribute(workspace, datatype)
                err_status = self.geoserver.publish_vector_time_dimensions(workspace, layer_name, layer_title, time_attribute)
                ts = self.dsm.get_timestamps_from_vector(layer_name, time_attribute)
                if ts:
                    timestamps = ts
                if not err_status:
                    LOG.info(f"Layer {layer_name} successfully updated with TIME dimension!")
        except Exception as e:
            err_status = str(e)
            LOG.error(e)
        return LayerPublicationStatus(
            is_container=False,
            original_name=layer_name,
            layer_name=layer_name,
            exception=err_status,
            datatype=datatype,
            timestamps=[] if err_status else timestamps,
        )

    def style_layer(self, workspace: str, layer_name: str, datatype: str):
        try:
            style = self.dsm.get_layer_style(workspace=workspace, datatype_id=datatype)
        except AttributeError:
            LOG.info(f"Style for datatype id {datatype} not found")
            style = None
        if style is not None:
            try:
                self.geoserver.publish_style(layer_name=layer_name, style_name=style, workspace=workspace)
            except Exception as e:
                LOG.error(e)

    def publish_from_db(
        self, workspace: str, store_name: str, layer_name: str, layer_title: str, datatype: str, start_time: datetime
    ) -> List[LayerPublicationStatus]:
        self.create_workspace(workspace)
        self.create_store(store_name, workspace)
        res = self.publish_table(workspace, store_name, layer_name, layer_title, datatype, start_time)
        if res.success:
            self.style_layer(workspace, res.layer_name, res.datatype)
        return [res]

    def publish_from_location(
        self, workspace: str, layer_name: str, layer_title: str, storage_location: str, datatype: str, start_time: datetime, mosaic: bool
    ) -> List[LayerPublicationStatus]:
        self.create_workspace(workspace)
        params = self.dsm.get_parameters(workspace, datatype)
        LOG.info(f"Publishing layer {layer_name} from location {storage_location}")
        netcdf_dt_rewrite = self.dsm.get_netcdf_layers(workspace=workspace, master_datatype_id=datatype)
        result = self.geoserver.create_coveragestore_patched(
            path=storage_location,
            datatype=datatype,
            start_time=start_time,
            coveragestore_name=layer_name,
            coveragestore_title=layer_title,
            workspace=workspace,
            external=True,
            netcdf_dt_rewrite=netcdf_dt_rewrite,
            mosaic=mosaic,
            params=params,
        )
        for res in result:
            if res.success:
                self.style_layer(workspace, res.layer_name, res.datatype)
                LOG.info(f"Layer {res.layer_name} successfully published from location!")
            else:
                LOG.error(res.exception)

        return result

    def delete_layer(self, workspace: str, layer_name: str, store_name: str, is_coveragestore: bool):
        LOG.info(f"Deleting layer {workspace}:{layer_name}")
        result = self.geoserver.delete_layer(workspace=workspace, layer_name=layer_name)
        if result:
            LOG.error(result)
        if is_coveragestore:
            result = self.geoserver.delete_coveragestore(workspace=workspace, coveragestore_name=store_name)
            if result:
                LOG.error(result)

    async def get_feature_info(self, session, url, params):
        """
        example result:
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "",
                    "geometry": null,
                    "properties": {
                        "t2m": 16.830000000000002
                    }
                }
            ],
            "totalFeatures": "unknown",
            "numberReturned": 1,
            "timeStamp": "2022-12-23T15:35:30.661Z",
            "crs": null
        }
        """
        LOG.info(f"GetFeatureInfo, url: {url}: {params}")
        async with session.get(url, params=params) as response:
            data = await response.json()
            res = []
            try:
                LOG.info(f"GetFeatureInfo, response check: {requests.get(url, params=params).json()}")
                # LOG.debug(f'GetFeatureInfo, response: {data}')
                features = data["features"]
                if len(features):
                    res = [feature.get("properties", {}) for feature in features]
                    LOG.info(f"GetFeatureInfo, res: {res}")
            except Exception as e:
                LOG.error(f"Error: {str(e)}")
                res = []

            LOG.info(f"GetFeatureInfo, return res: {res}")
            return res

    async def get_timeseries_from_featureinfo(
        self, workspace: str, resources: list, bbox: str, crs: str, timestamps: list
    ):
        url = f"{self.service_url}/{workspace}/wms"
        data = None

        async with aiohttp.ClientSession() as session:
            tasks = []
            for res in resources:
                layer_name = f"{workspace}:{res.layer_name}"
                params = {
                    "SERVICE": "WMS",
                    "VERSION": "1.1.1",
                    "REQUEST": "GetFeatureInfo",
                    "QUERY_LAYERS": layer_name,
                    "LAYERS": layer_name,
                    "INFO_FORMAT": "application/json",
                    "FEATURE_COUNT": 50,
                    "X": 50,
                    "Y": 50,
                    "SRS": crs,
                    "WIDTH": 101,
                    "HEIGHT": 101,
                    "BBOX": bbox,
                    "TIME": res.timestamps.replace(";", ","),
                }
                tasks.append(asyncio.ensure_future(self.get_feature_info(session, url, params)))

            data = await asyncio.gather(*tasks)
            # flat list of list of dicts
            data = list(chain.from_iterable(data))
        LOG.info(f"data from featureinfo: {data}")

        LOG.info(f"Finalized all. Return is a list of len {len(data)} outputs.")
        LOG.info(data)

        df = pd.DataFrame(data)
        try:
            df.index = pd.to_datetime(df["timestamp"])
            df.drop(columns=["timestamp"], inplace=True)
        except KeyError:
            df.index = list(chain.from_iterable(timestamps))
        try:
            df.drop(columns="Index", inplace=True)
        except KeyError:
            pass

        # drop duplicates, keep values from last created file        
        df = df[~df.index.duplicated(keep='last')]
        
        df.sort_index(inplace=True)
        return df

    async def get_timeseries(self, session, url, params):
        """
        example result:
        # Latitude: 45.959006934741176
        # Longitude: 8.805176976032786
        Time (UTC),ermes:31105_tp24_31001_24a1f9c4-19d3-4c82-abbc-7517a7a12e29
        2023-01-03T07:00:00.000Z,1.628875732421875
        2023-01-03T08:00:00.000Z,2.0847320556640625
        2023-01-03T09:00:00.000Z,2.44903564453125
        2023-01-03T10:00:00.000Z,2.674102783203125
        2023-01-03T11:00:00.000Z,2.777099609375
        2023-01-03T12:00:00.000Z,2.819061279296875
        2023-01-03T13:00:00.000Z,2.76947021484375
        """
        LOG.info(f"GetTimeseries, params {params}")
        try:
            var_name = params["LAYERS"].split("_")[1]
        except Exception:
            var_name = "variable"
        async with session.get(url, params=params) as response:
            data = await response.text()
            LOG.info(f"GetTimeseries, response: {data}")
            return pd.read_csv(io.StringIO(data), sep=",", skiprows=2, index_col=0, header=0, names=[var_name])

    async def get_timeseries_from_netcdf(self, workspace: str, layers: list, bbox: str, crs: str, timestamps: list):
        url = f"{self.service_url}/{workspace}/wms"
        dfs = []

        async with aiohttp.ClientSession() as session:
            tasks = []
            for layer, ts in zip(layers, timestamps):
                layer_name = f"{workspace}:{layer}"

                # If length > 100, must be split in two requests
                ts_list = list(self.divide_chunks(ts, 100))

                for ts_ in ts_list:
                    params = {
                        "SERVICE": "WMS",
                        "VERSION": "1.1.0",
                        "REQUEST": "GetTimeSeries",
                        "QUERY_LAYERS": layer_name,
                        "LAYERS": layer_name,
                        "INFO_FORMAT": "text/csv",
                        "FEATURE_COUNT": 1,
                        "X": 1,
                        "Y": 1,
                        "SRS": crs,
                        "WIDTH": 1,
                        "HEIGHT": 1,
                        "BBOX": bbox,
                        "TIME": ",".join(ts_),
                    }
                    tasks.append(asyncio.ensure_future(self.get_timeseries(session, url, params)))

            dfs = await asyncio.gather(*tasks)

        data = pd.concat(dfs)
        data = data[~data.index.duplicated(keep="last")]  # remove duplicates
        LOG.info(f"Finalized all. Return is a list of len {len(data)} outputs.")

        return data

    @staticmethod
    def divide_chunks(l, n):  # noqa: E741
        # looping till length l
        for i in range(0, len(l), n):
            yield l[i : i + n]
