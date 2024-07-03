import json
import logging
import os
from datetime import datetime
from functools import reduce
from typing import List, Optional
import pathlib
import numpy
import requests
import xarray
from geo.Geoserver import Geoserver

from importer.dto.layer_publication_status import LayerPublicationStatus
from importer.util.datetimeutils import isoformat_Z, set_utc_default_tz

LOG = logging.getLogger(__name__)


class GeoserverREST(Geoserver):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._session = requests.Session()
        self._session.auth = (self.username, self.password)

    @property
    def session(self):
        return self._session

    def __featuretype_withtime(self, workspace: str, featuretype: str, title:str, time_attribute: str):
        url = f"{self.service_url}/rest/workspaces/{workspace}/featuretypes/{featuretype}.json"
        data = {
            "featureType": {
                "name": featuretype,
                "nativeName": featuretype,
                "title": title if title else featuretype,
                "enabled": True,
                "metadata": {
                    "entry": [
                        {
                            "@key": "time",
                            "dimensionInfo": {
                                "enabled": True,
                                "attribute": time_attribute,
                                "presentation": "LIST",
                                "units": "ISO8601",
                                "defaultValue": "",
                                "nearestMatchEnabled": False,
                                "rawNearestMatchEnabled": False,
                            },
                        }
                    ]
                },
            }
        }
        return url, data

    def __packcoverageview(
        self, workspace: str, coveragestore_name: str, layer_name: str, bands: List[str], datatypeid: str, withtime=False
    ):
        url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{coveragestore_name}/coverages"
        nativedatatype = reduce(lambda a, b: a + b, bands)
        coveragename = f"{datatypeid}_{nativedatatype}_{coveragestore_name}"
        data = {
            "coverage": {
                "name": coveragename,
                "title": layer_name if layer_name else coveragename,
                "nativeName": coveragestore_name,
                "metadata": {
                    "entry": [
                        {
                            "@key": "COVERAGE_VIEW",
                            "coverageView": {
                                "name": coveragestore_name,
                                "envelopeCompositionType": "INTERSECTION",
                                "selectedResolution": "BEST",
                                "selectedResolutionIndex": -1,
                                "coverageBands": {
                                    "coverageBand": [
                                        {
                                            "inputCoverageBands": {
                                                "@class": "singleton-list",
                                                "inputCoverageBand": [{"coverageName": band, "band": 0}],
                                            },
                                            "definition": f"{coveragestore_name}@{bandnum}",
                                            "index": bandnum,
                                            "compositionType": "BAND_SELECT",
                                        }
                                        for bandnum, band in enumerate(bands)
                                    ]
                                },
                            },
                        }
                    ]
                },
                "dimensions": {
                    "coverageDimension": [
                        {
                            "name": band,
                            "description": "GridSampleDimension[-Infinity,Infinity]",
                            "range": {"min": "-inf", "max": "inf"},
                            "dimensionType": {"name": "REAL_32BITS"},
                        }
                        for band in bands
                    ]
                },
            }
        }
        if withtime:
            data["coverage"]["metadata"]["entry"] += {
                "@key": "time",
                "dimensionInfo": {"enabled": True, "presentation": "LIST", "units": "ISO8601", "defaultValue": ""},
            }
        return url, data, coveragename

    def __create_gwc_layer_withtime(self, workspace: str, coveragename: str):
        data = None
        w_coveragename = f"{workspace}:{coveragename}"
        url = f"{self.service_url}/gwc/rest/layers/{w_coveragename}"

        # get the gwc layer configuration
        data = {
            "GeoServerLayer": {
                "enabled": True,
                "inMemoryCached": True,
                "name": w_coveragename,
                "mimeFormats": {"string": ["image/png", "image/jpeg"]},
                "gridSubsets": {"gridSubset": [{"gridSetName": "EPSG:4326"}, {"gridSetName": "EPSG:900913"}]},
                "metaWidthHeight": {"int": ["4", "4"]},
                "expireCache": "0",
                "expireClients": "0",
                "parameterFilters": {
                    "regexParameterFilter": {
                        "regex": "[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}.[0-9]+Z",
                        "defaultValue": "",
                        "normalize": {"locale": ""},
                        "key": "TIME",
                    },
                    "styleParameterFilter": {"key": "STYLES", "defaultValue": ""},
                },
                "gutter": "0",
                "cacheWarningSkips": "",
            }
        }

        return url, data

    def __packcoverage(
        self, workspace: str, coveragestore_name: str, coveragestore_title: str, nativename: str, datatypeid: str, withtime=False
    ):
        url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{coveragestore_name}/coverages"
        coveragename = f"{datatypeid}_{nativename}_{coveragestore_name}"
        title = f"{nativename} {coveragestore_title}"
        data = {
            "coverage": {
                "name": coveragename,
                "title": title,
                "nativeCoverageName": nativename,
                "dimensions": {
                    "coverageDimension": {
                        "name": nativename,
                        "description": "GridSampleDimension[-Infinity,Infinity]",
                        "range": {"min": "-inf", "max": "inf"},
                        "dimensionType": {"name": "REAL_32BITS"},
                    }
                },
            }
        }
        if withtime:
            data["coverage"]["metadata"] = {
                "entry": [
                    {
                        "@key": "time",
                        "dimensionInfo": {
                            "enabled": True,
                            "presentation": "LIST",
                            "units": "ISO8601",
                            "defaultValue": "",
                        },
                    }
                ]
            }
        return url, data, coveragename

    def __create_coveragestore_netcdf_dt_rewrite(
        self,
        path: str,
        store_type: str,
        workspace: str,
        coveragestore_name: str,
        coveragestore_title: str,
        datatype: str,
        netcdf_dt_rewrite: list,
    ):
        publication_statuses = []
        timestamps = []

        url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores"
        data = {
            "coverageStore": {
                "enabled": True,
                "type": "NetCDF",
                "workspace": workspace,
                "name": coveragestore_name,
                "url": f"file:{path}",
            }
        }

        try:
            r = self.session.post(url, json=data)
            if r.status_code == 201:
                err_string = None
                timestamps = [
                    numpy.datetime_as_string(t, unit="ms", timezone="UTC")
                    for t in xarray.open_dataset(path).load().time.data
                ]
            else:
                err_string = f"{r.status_code}: The coveragestore can not be created! {r.text}"
        except Exception as e:
            err_string = f"Error: {e}"

        publication_statuses.append(
            LayerPublicationStatus(True, coveragestore_name, coveragestore_name, err_string, datatype, timestamps)
        )
        # If coverage store publish failed, do not attempt with single coverages
        if err_string is not None:
            return publication_statuses

        for pairmap in netcdf_dt_rewrite:
            if len(pairmap["native"].split(",")) > 1:
                # not used anymore
                url, data, coveragename = self.__packcoverageview(
                    workspace,
                    coveragestore_name,
                    coveragestore_title,
                    pairmap["native"],
                    pairmap["rename"],
                    withtime=pairmap["time_dimension"],
                )
            else:
                url, data, coveragename = self.__packcoverage(
                    workspace,
                    coveragestore_name,
                    coveragestore_title,
                    pairmap["native"],
                    pairmap["rename"],
                    withtime=pairmap["time_dimension"],
                )
            try:
                r = self.session.post(url, json=data)
                if r.status_code == 201:
                    err_string = None
                else:
                    err_string = f"{r.status_code}: The coveragestore can not be created! {r.text}"
            except Exception as e:
                err_string = f"Error: {e}"
            publication_statuses.append(
                LayerPublicationStatus(
                    False, coveragestore_name, coveragename, err_string, pairmap["rename"], timestamps
                )
            )

            # update gwc layer with time
            url, data = self.__create_gwc_layer_withtime(workspace, coveragename)
            try:
                r = self.session.post(url, json=data)
                if r.status_code / 100 == 2:
                    err_string = None
                else:
                    err_string = (
                        f"{r.status_code}: The gwc layer can not be updated with TIME parameter! {r.text}, "
                        f"url: {url}, data: {data}"
                    )
            except Exception as e:
                err_string = f"Error: {e}"

        return publication_statuses

    def __create_coveragestore_common(
        self,
        path: str,
        store_type: str,
        workspace: str,
        coveragestore_name: str,
        coveragestore_title: str,
        datatype: str,
        content_type: str,
        configure: str,
        file_type: str,
        start_time: datetime,
    ):
        url = (
            f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/"
            f"{coveragestore_name}/{store_type}.{file_type}"
        )
        headers = {"Content-type": content_type, "Accept": "application/xml"}
        params = {"configure": 'none'}
        # if configure != "all":
        #     params["coverageName"] = coveragestore_name
        LOG.info(f"url: {url}, headers: {headers}, params: {params}, data: {path}")
        try:
            r = self.session.put(url, data=path, headers=headers, params=params)
            if r.status_code == 201:
                self.__create_layer_from_store(workspace, path, coveragestore_name, coveragestore_title)
                err_string = None
            else:
                err_string = f"{r.status_code}: The coveragestore can not be created! {r.text}"
        except Exception as e:
            err_string = f"Error: {e}"

        return [
            LayerPublicationStatus(
                is_container=False,
                original_name=coveragestore_name,
                layer_name=coveragestore_name,
                exception=err_string,
                datatype=datatype,
                timestamps=([] if err_string else [isoformat_Z(set_utc_default_tz(start_time))]),
            )
        ]
    
    def __create_layer_from_store(self, workspace: str, path: str, coveragestore_name: str, coveragestore_title: str):
        url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{coveragestore_name}/coverages"
        body = {
            "coverage": {
                "nativeName": coveragestore_name,
                "title": coveragestore_title,
                "nativeCoverageName": pathlib.Path(path).stem
            }
        }
        headers = {"Content-type": "application/json"}

        LOG.info(f"url: {url}, body: {body}")
        try:
            r = self.session.post(url, headers=headers, data=json.dumps(body))
            if r.status_code != 201:
                raise Exception(f"{r.status_code}: {r.text}")
        except Exception as e:
            raise Exception(f"Error: {e}")

    def __create_coveragestore_mosaic(
        self, path: str, workspace: str, coveragestore_name: str, coveragestore_title: str, datatype: str, start_time: datetime
    ):
        publication_statuses = []
        timestamps = [isoformat_Z(set_utc_default_tz(start_time))]

        url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores"
        data = {
            "coverageStore": {
                "enabled": True,
                "type": "ImageMosaic",
                "workspace": workspace,
                "name": coveragestore_name,
                "url": f"file:{path}",
            }
        }

        try:
            r = self.session.post(url, json=data)
            if r.status_code == 201:
                err_string = None
            else:
                err_string = f"{r.status_code}: The coveragestore can not be created! {r.text}"
        except Exception as e:
            err_string = f"Error: {e}"

        publication_statuses.append(
            LayerPublicationStatus(
                True,
                coveragestore_name,
                coveragestore_name,
                err_string,
                datatype,
                timestamps=([] if err_string else timestamps),
            )
        )

        if err_string is not None:
            return publication_statuses

        url = f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{coveragestore_name}/coverages"
        coveragename = f"{coveragestore_name}"
        data = {"coverage": {"name": coveragename, "title": coveragestore_title, "nativeFormat": "ImageMosaic"}}

        try:
            r = self.session.post(url, json=data)
            if r.status_code == 201:
                err_string = None
            else:
                err_string = f"{r.status_code}: The coveragestore can not be created! {r.text}"
        except Exception as e:
            err_string = f"Error: {e}"

        publication_statuses.append(
            LayerPublicationStatus(
                False,
                coveragestore_name,
                coveragename,
                err_string,
                datatype,
                timestamps=([] if err_string else timestamps),
            )
        )

        return publication_statuses

    def create_coveragestore_patched(
        self,
        path: str,
        datatype: str,
        start_time: datetime,
        workspace: Optional[str] = None,
        coveragestore_name: Optional[str] = None,
        coveragestore_title: Optional[str] = None,
        netcdf_dt_rewrite: Optional[list] = None,
        external: bool = False,
        mosaic: bool = False,
        params: dict = None,
    ):
        """
        Monkey patch to fix a bug in this method.
        Creates the coveragestore; Data will uploaded to the server.
        Parameters
        ----------
        path : str
        workspace : str, optional
        layer_name : str, optional
            The name of coveragestore. If not provided, parsed from the file name.
        file_type : str
        external : bool
        Notes
        -----
        the path to the file and file_type indicating it is a geotiff, arcgrid or other raster type
        """

        if path is None:
            raise Exception("You must provide the full path to the raster")

        if workspace is None:
            workspace = "default"

        if coveragestore_name is None:
            coveragestore_name = os.path.basename(path)
            f = coveragestore_name.split(".")
            if len(f) > 0:
                coveragestore_name = f[0]

        content_type = "image/tiff" if not external else "text/plain"
        store_type = "file" if not external else "external"
        file_type = "netcdf" if path.split(".")[-1] in ["nc", "ncml"] else "geotiff"

        if mosaic:
            layer_list = self.__create_coveragestore_mosaic(path, workspace, coveragestore_name, coveragestore_title, datatype, start_time)
            self.__apply_params(workspace, coveragestore_name, params)
        elif file_type == "netcdf":  # and netcdf_dt_rewrite is not None:
            layer_list = self.__create_coveragestore_netcdf_dt_rewrite(
                path, store_type, workspace, coveragestore_name, coveragestore_title, datatype, netcdf_dt_rewrite
            )
        # elif file_type == 'netcdf':
        #    return self.__create_coveragestore_common(path, store_type, workspace, coveragestore_name, datatype,
        #       content_type, 'all', 'netcdf')
        elif file_type == "geotiff":
            layer_list = self.__create_coveragestore_common(
                path, store_type, workspace, coveragestore_name, coveragestore_title, datatype, content_type, "first", "geotiff", start_time
            )
            self.__apply_params(workspace, coveragestore_name, params)
        else:
            return [
                LayerPublicationStatus(
                    False, coveragestore_name, coveragestore_name, f"Filetype not supported: {file_type}", None, []
                )
            ]

        return layer_list

    def publish_vector_time_dimensions(self, workspace: str, featuretype: str, title: str, time_attribute: str):
        LOG.info(f"time attribute: {time_attribute}")
        status = None
        if not time_attribute:
            status = f"TIME_ATTRIBUTE not specified for layer {featuretype} not specified!"
            LOG.error(f"time attribute: {time_attribute}")
        else:
            url, data = self.__featuretype_withtime(workspace, featuretype, title, time_attribute)
            try:
                r = self.session.put(url, json=data)
                if r.status_code / 100 == 2:
                    status = None
                else:
                    status = (
                        f"{r.status_code}: The featuretype can not be updated with TIME parameter! {r.text},"
                        f"url: {url}, data: {data}"
                    )
                    LOG.error(f"status: {status}")
            except Exception as e:
                status = f"Error: {e}"
                LOG.error(f"status: {status}")

        return status

    def __apply_params(self, workspace: str, coveragestore_name: str, params: dict = None):
        if params is None:
            return None

        url = (
            f"{self.service_url}/rest/workspaces/{workspace}/coveragestores/{coveragestore_name}/"
            f"coverages/{coveragestore_name}.json"
        )
        headers = {"Content-type": "application/json"}
        data = {
            "coverage": {
                "name": coveragestore_name,
                "parameters": {"entry": [{"string": [key, params[key]]} for key in params.keys()]},
            }
        }
        LOG.info(f"data: {data}")
        try:
            r = self.session.put(url, data=json.dumps(data), headers=headers)
            if r.status_code == 200:
                err_status = None
                LOG.info(f"Changes applied successfully to coveragestore: {coveragestore_name}")
            else:
                err_status = f"{r.status_code}: The params can not be updated! {r.text}. {url}"
                LOG.error(f"error status for coveragestore {coveragestore_name}: {err_status}")
        except Exception as e:
            err_status = f"Error: {e}"
            LOG.error(f"error status for coveragestore {coveragestore_name}: {err_status}")
        return err_status
