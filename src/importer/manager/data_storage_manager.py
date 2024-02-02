import glob
import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import geopandas as gpd
import rasterio.features
import tifffile
from geoalchemy2.shape import from_shape
from importer.database.extensions import db_session
from importer.database.models import GeoserverResource, LayerSettings
from importer.database.schemas import (
    DownloadedDataSchema,
    GeoserverResourceSchema,
    LayerSettingsSchema,
)
from importer.database.session import SessionLocal
from importer.driver.postgis_driver import PostGISDriver
from importer.dto.layer_publication_status import LayerPublicationStatus
from importer.settings.instance import settings
from importer.util.datetimeutils import isoformat_Z
from rasterio.transform import from_origin
from shapely.geometry import shape
from shapely.geometry.multipolygon import MultiPolygon
from shapely.geometry.polygon import Polygon
from sqlalchemy import func
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.orm.session import Session
from sqlalchemy.sql.schema import Column
from sqlalchemy.sql.sqltypes import DateTime

LOG = logging.getLogger(__name__)


class DataStorageManager:
    def __init__(self):
        self.driver = PostGISDriver()
        self.geoserver_file_storage_dir = settings.geoserver_data_dir
        self.geoserver_tif_folder = settings.geoserver_tif_folder
        self.geoserver_workspace = settings.geoserver_workspace
        self.geoserver_imagemosaic_folder = settings.geoserver_imagemosaic_folder

    def save_resources(
        self, data_list: List[DownloadedDataSchema], vectorize_tif: bool = False
    ) -> List[GeoserverResourceSchema]:
        all_saved_resources = []
        for data in data_list:
            try:
                all_saved_resources = self.save_to_db(data, all_saved_resources, vectorize_tif)
                all_saved_resources = self.save_to_file_storage(data, all_saved_resources, vectorize_tif)
            except Exception as e:
                raise e
            finally:
                shutil.rmtree(data.tmp_path, ignore_errors=True)
        LOG.info(f'{len(all_saved_resources)} resource{"s" if len(all_saved_resources) != 1 else ""} saved on db')
        return all_saved_resources

    def save_to_db(
        self, data: DownloadedDataSchema, all_saved_resources: List[GeoserverResource], vectorize_tif: bool
    ):
        try:
            gpd_dfs, saved_resources = self.convert_to_gpd(data, vectorize_tif)
        except Exception as e:
            LOG.error(str(e))
            return all_saved_resources
        for gpd_df, saved_resource in zip(gpd_dfs, saved_resources):
            try:
                self.driver.save_table(gpd_df=gpd_df, table_name=saved_resource.layer_name)
            except Exception:
                try:
                    # If table already exists, overwrite it
                    self.driver.drop_table(table_name=saved_resource.layer_name)
                    self.driver.save_table(gpd_df, table_name=saved_resource.layer_name)
                except Exception as e:
                    LOG.error(f"Failed to save geopandas dataframe in table {saved_resource.layer_name}: {str(e)}")
                    continue
            all_saved_resources.append(saved_resource)
        return all_saved_resources

    def dumps_json(self, x):
        if isinstance(x, dict):
            return json.dumps(x)
        else:
            return x

    def convert_to_gpd(
        self, data: DownloadedDataSchema, vectorize_tif: bool
    ) -> Tuple[List[gpd.GeoDataFrame], List[GeoserverResourceSchema]]:
        gpd_dfs, saved_resources = [], []
        for ext in ["shp", "json", "geojson"]:
            for index, filename in enumerate(glob.glob(os.path.join(data.tmp_path, f"**/*.{ext}"), recursive=True)):
                try:
                    gdf = gpd.read_file(filename)
                    gpd_dfs.append(gdf.applymap(lambda x: self.dumps_json(x)))
                    saved_resource = self.pack_resource(data, index)
                    saved_resources.append(saved_resource)
                except Exception as e:
                    LOG.error(str(e))
                    continue
        for index, filename in enumerate(glob.glob(os.path.join(data.tmp_path, "**/*.kml"), recursive=True)):
            try:
                gpd.io.file.fiona.drvsupport.supported_drivers["KML"] = "rw"
                gpd_dfs.append(gpd.read_file(filename, driver="KML"))
                saved_resource = self.pack_resource(data, index)
                saved_resources.append(saved_resource)
            except Exception as e:
                LOG.error(str(e))
                continue
        if vectorize_tif and not data.mosaic:  # TODO improve, does not work well. Not used for now
            for ext in ["tif", "tiff"]:
                for index, filename in enumerate(
                    glob.glob(os.path.join(data.tmp_path, f"**/*.{ext}"), recursive=True)
                ):
                    try:
                        with tifffile.TiffFile(filename) as tif:
                            for index, page in enumerate(tif.pages):
                                geometry = []
                                image = page.asarray().astype("uint8")
                                xmin, ymin, xres, yres = 0, 0, 0, 0
                                # Extract the tags of the image containing the bbox bottom-left coordinate
                                # (in WGS84 coordinate system) and the spatial resolution of the image
                                for tag in tif.pages[0].tags.values():
                                    if tag.name == "ModelTiepointTag":
                                        _, _, _, xmin, ymin, _ = tag.value
                                    if tag.name == "ModelPixelScaleTag":
                                        xres, yres, _ = tag.value
                                geotransform = (xmin, ymin, xres, yres)
                                for shp, _ in rasterio.features.shapes(image, transform=from_origin(*geotransform)):
                                    geometry.append(shape(shp))
                                gpd_dfs.append(gpd.GeoDataFrame(geometry=geometry))
                                saved_resource = self.pack_resource(data, index)
                                saved_resources.append(saved_resource)
                    except Exception as e:
                        LOG.error(str(e))
                        continue
        return gpd_dfs, saved_resources

    def save_to_file_storage(
        self, data: DownloadedDataSchema, all_saved_resources: List[GeoserverResource], vectorize_tif: bool
    ):
        if not vectorize_tif or data.mosaic:
            for ext in ["tif", "tiff"]:
                if data.mosaic:
                    base_path = os.path.join(
                        self.geoserver_file_storage_dir,
                        self.geoserver_imagemosaic_folder,
                        f"{data.datatype_id}_{data.resource_id}",
                    )
                else:
                    base_path = os.path.join(self.geoserver_file_storage_dir, self.geoserver_tif_folder)
                # Create folder if it does not exist
                os.makedirs(base_path, exist_ok=True)
                os.chmod(base_path, 0o777)
                index = -1
                for index, filepath in enumerate(
                    glob.glob(os.path.join(data.tmp_path, f"**/*.{ext}"), recursive=True)
                ):
                    # Build file storage location
                    storage_location = os.path.join(base_path, f"{data.datatype_id}_{data.resource_id}_{index}.{ext}")
                    # Save file to storage location
                    shutil.copyfile(filepath, storage_location)
                    LOG.info(storage_location)
                    if not data.mosaic:
                        saved_resource = self.pack_resource(data, index, storage_location)
                        all_saved_resources.append(saved_resource)
                if data.mosaic and index >= 0:
                    saved_resource = self.pack_resource(data, 0, base_path)
                    all_saved_resources.append(saved_resource)
        for ext in ["nc", "ncml"]:
            for index, filepath in enumerate(glob.glob(os.path.join(data.tmp_path, f"**/*.{ext}"), recursive=True)):
                # There is no a folder for NetCDF, since the geoserver NetCDF plugin creates a couple of auxiliary
                # files and there would be permission issues
                # Look here for what would happen: https://geoserver-users.narkive.com/e9trt6wx/error-when-creating-netcdf-store
                # TODO correctly manage permission to geoserver user and make a folder for NetCDF files
                storage_location = os.path.join(
                    self.geoserver_file_storage_dir, f"{data.datatype_id}_{data.resource_id}.{ext}"
                )
                Path(os.path.join(*storage_location.split("/")[:-1])).mkdir(parents=True, exist_ok=True)
                shutil.copyfile(filepath, storage_location)
                LOG.info(storage_location)
                # Save resource on db
                saved_resource = self.pack_resource(data, index, storage_location)
                all_saved_resources.append(saved_resource)
        return all_saved_resources

    def pack_resource(self, data: DownloadedDataSchema, index: int, storage_location=None) -> GeoserverResourceSchema:
        """Save a new resource entry on PostGIS db"""
        geometry = shape(data.bbox).buffer(0)
        if isinstance(geometry, Polygon):
            geometry = MultiPolygon([geometry])
        bbox = from_shape(geometry, srid=4326)
        packed_resource = GeoserverResourceSchema(
            datatype_id=data.datatype_id,
            workspace_name=self.geoserver_workspace,
            store_name=data.store_name if data.store_name else f"{data.datatype_id}_{data.resource_id}",
            layer_name=f'{data.datatype_id}_{data.resource_id}{f"_{index}" if index > 0 else ""}',
            storage_location=storage_location,
            expire_on=None,
            start=data.start,
            end=data.end,
            creation_date=data.creation_date,
            resource_id=data.resource_id,
            metadata_id=data.metadata_id,
            request_code=data.request_code,
            bbox=bbox,
            mosaic=data.mosaic,
        )

        return packed_resource

    def add_resources_entries(
        self, resources: List[GeoserverResourceSchema], all_pubstatus: List[LayerPublicationStatus]
    ) -> GeoserverResourceSchema:
        """Save the resource entries on PostGIS db"""
        resource_dict = {}

        for resource in resources:
            resource_dict[resource.layer_name] = resource

        for pubstatus in all_pubstatus:
            resource = resource_dict[pubstatus.original_name]

            if pubstatus.success and pubstatus.is_layer:
                with db_session() as session:
                    saved_resource = GeoserverResource(
                        datatype_id=pubstatus.datatype,
                        workspace_name=self.geoserver_workspace,
                        store_name=resource.store_name,
                        layer_name=pubstatus.layer_name,
                        storage_location=resource.storage_location,
                        expire_on=resource.expire_on,
                        start=resource.start,
                        end=resource.end,
                        created_at=resource.creation_date,
                        resource_id=resource.resource_id,
                        metadata_id=resource.metadata_id,
                        request_code=(
                            resource.request_code
                            if resource.request_code and len(resource.request_code.strip()) > 0
                            else None
                        ),
                        bbox=resource.bbox,
                        mosaic=resource.mosaic,
                        timestamps=";".join(pubstatus.timestamps),
                    )
                    session.add(saved_resource)
                    session.flush()

    def get_resources(
        self,
        session: Session,
        datatype_ids: Optional[List[str]] = None,
        resource_id: Optional[str] = None,
        expire_on: Optional[DateTime] = None,
        order_by: Optional[Column] = None,
        created_before: Optional[DateTime] = None,
    ) -> List[GeoserverResource]:
        statement = session.query(GeoserverResource).filter(GeoserverResource.deleted_at.is_(None))
        if datatype_ids:
            statement = statement.filter(GeoserverResource.datatype_id.in_(datatype_ids))
        if resource_id:
            statement = statement.filter(GeoserverResource.resource_id == resource_id)
        if created_before:
            statement = statement.filter(GeoserverResource.created_at <= created_before)
        if expire_on:
            statement = statement.filter(GeoserverResource.expire_on.isnot(None)).filter(
                GeoserverResource.expire_on <= expire_on
            )
        if order_by:
            statement = statement.order_by(order_by)
        return statement.all()

    def get_layer_settings(
        self,
        session,
        master_datatype_id: str = None,
        datatype_id: str = None,
        var_name: str = None,
        style: Optional[str] = None,
        delete_after_days: Optional[int] = None,
        delete_after_count: Optional[int] = None,
    ) -> LayerSettingsSchema:
        """
        Retrieves the layer settings based on the provided parameters.

        Args:
            session: The session object used to query the database.
            master_datatype_id (optional): The master datatype ID to filter the layer settings by.
            datatype_id (optional): The datatype ID to filter the layer settings by.
            var_name (optional): The variable name to filter the layer settings by.
            style (optional): The style to filter the layer settings by.
            delete_after_days (optional): The number of days after which the layer settings should be deleted.
            delete_after_count (optional): The number of times the layer settings should be deleted.

        Returns:
            LayerSettingsSchema: The layer settings matching the provided parameters.
            If master_datatype_id is provided, the result will be a list of LayerSettingsSchema objects.

        Raises:
            NoResultFound: If no layer settings are found with the provided datatype ID.

        """

        statement = session.query(LayerSettings)
        if master_datatype_id:
            statement = statement.filter(LayerSettings.master_datatype_id == master_datatype_id)
        if datatype_id:
            statement = statement.filter(LayerSettings.datatype_id == datatype_id)
        if var_name:
            statement = statement.filter(LayerSettings.var_name == var_name)
        if style:
            statement = statement.filter(LayerSettings.style == style)
        if delete_after_days:
            statement = statement.filter(LayerSettings.delete_after_days == delete_after_days)
        if delete_after_count:
            statement = statement.filter(LayerSettings.delete_after_count == delete_after_count)

        try:
            if master_datatype_id:
                result = statement.all()
            else:
                result = statement.one()
        except NoResultFound:
            LOG.error(f"No result was found with datatype id: {datatype_id}")
            result = None

        LOG.debug(result)
        return result

    def get_layer_style(self, datatype_id: str = None) -> str:
        with db_session() as session:
            result = self.get_layer_settings(session, datatype_id=datatype_id)
            try:
                style = result.style
            except AttributeError:
                style = None
                LOG.error(f"Style not found for datatype id: {datatype_id}")

        return style

    def has_time_dimension(self, datatype_id: str = None) -> str:
        with db_session() as session:
            result = self.get_layer_settings(session, datatype_id=datatype_id)
            try:
                time_dim = result.time_dimension
                LOG.info(f"time dimension for datatype id {datatype_id}: {time_dim}")
            except AttributeError:
                time_dim = None
                LOG.error(f"time dimension not found for datatype id: {datatype_id}")

        return time_dim

    def get_netcdf_layers(self, master_datatype_id):
        layers = []
        with db_session() as session:
            result = self.get_layer_settings(session, master_datatype_id=master_datatype_id)
            try:
                # create list of value couple (datatype_id, var_name) if datatype_id is not None
                for r in result:
                    if r.datatype_id:
                        layers.append(
                            {"native": r.var_name, "rename": r.datatype_id, "time_dimension": r.time_dimension}
                        )
            except AttributeError:
                LOG.error(f"No settings found for datatype id: {master_datatype_id}")
                pass
        if not layers:
            layers = None
        return layers

    def get_parameters(self, datatype_id: str = None) -> str:
        par = None
        with db_session() as session:
            result = self.get_layer_settings(session, datatype_id=datatype_id)
            try:
                par = json.loads(result.parameters)
                LOG.info(f"parameters for datatype id {datatype_id}: {par}")
            except AttributeError:
                par = None
                LOG.error(f"parameters not found for datatype id: {datatype_id}")
            except (ValueError, TypeError):
                par = None
                LOG.info(f"parameters null or not in JSON format for datatype id: {datatype_id}. Ignoring...")

        return par

    def get_time_attribute(self, datatype_id: str = None) -> str:
        with db_session() as session:
            result = self.get_layer_settings(session, datatype_id=datatype_id)
            try:
                time_attribute = result.time_attribute
            except AttributeError:
                time_attribute = None
                LOG.error(f"time attribute not found for datatype id: {datatype_id}")

        return time_attribute

    def get_timestamps_from_vector(self, layer_name: str, time_attribute: str) -> list:
        if time_attribute is None:
            return []
        gdf = self.driver.get_table(layer_name)
        try:
            gdf_timestamps = gdf[time_attribute].map(lambda x: isoformat_Z(x))
            timestamps = sorted(list(gdf_timestamps.unique()))
            LOG.info(f"timestamps for layer {layer_name}: {timestamps}")
        except Exception:
            timestamps = []
            LOG.error(f"no timestamps for layer {layer_name}")
        LOG.info(f"timestamps for layer {layer_name}: {sorted(timestamps)}")
        return timestamps

    def countlayers_perresource(self, session: SessionLocal, resources: List[GeoserverResource]) -> Dict[str, int]:
        res = (
            session.query(GeoserverResource.resource_id, func.count(GeoserverResource.id))
            .filter(GeoserverResource.deleted_at.is_(None))
            .filter(GeoserverResource.resource_id.in_(list(set(r.resource_id for r in resources))))
            .group_by(GeoserverResource.resource_id)
            .all()
        )
        return {k: v for k, v in res}

    def delete_resources(
        self,
        session: SessionLocal,
        resources: List[GeoserverResource],
        resourcelayercount: Dict[str, int],
        remove: bool = False,
    ):
        rlc_copy = {k: v for k, v in resourcelayercount.items()}
        for resource in resources:
            try:
                LOG.info(f"Deleting layer {resource.layer_name} from db")
                if remove:
                    session.delete(resource)
                else:
                    resource.deleted_at = datetime.utcnow()
                session.flush()

                if resource.storage_location is None:
                    LOG.info(f"Dropping table {resource.layer_name} from db")
                    self.driver.drop_table(table_name=resource.layer_name)
                elif rlc_copy[resource.resource_id] == 1:
                    if os.path.isfile(resource.storage_location):
                        LOG.info(f"Deleting file {resource.storage_location}")
                        os.remove(resource.storage_location)
                    elif os.path.isdir(resource.storage_location):
                        LOG.info(f"Deleting folder {resource.storage_location}")
                        shutil.rmtree(resource.storage_location)

                rlc_copy[resource.resource_id] -= 1
            except Exception as e:
                LOG.error(str(e))

    @staticmethod
    def drop_empty_folders(directory):
        """Verify that every empty folder removed in local storage."""

        for dirpath, dirnames, filenames in os.walk(directory, topdown=False):
            if not dirnames and not filenames:
                os.rmdir(dirpath)
                os.rmdir(dirpath)
