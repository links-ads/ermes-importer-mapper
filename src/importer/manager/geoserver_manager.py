import logging
from typing import Dict, List

from importer.database.models import GeoserverResource
from importer.database.schemas import GeoserverResourceSchema
from importer.driver.geoserver_driver import GeoserverDriver
from importer.dto.layer_publication_status import LayerPublicationStatus
from importer.dto.layer_publication_status import LayerPublicationStatus

LOG = logging.getLogger(__name__)


class GeoserverManager:
    def __init__(self):
        self.driver = GeoserverDriver()

    def publish(self, resources: List[GeoserverResourceSchema]) -> List[LayerPublicationStatus]:
        all_pubstatus = []
        for resource in resources:
            if resource.storage_location:
                pubstatuses = self.driver.publish_from_location(
                    workspace=resource.workspace,
                    layer_name=resource.layer_name,
                    layer_title=resource.layer_title,
                    storage_location=resource.storage_location,
                    datatype=resource.datatype_id,
                    start_time=resource.start,
                    mosaic=resource.mosaic,
                )
            else:
                pubstatuses = self.driver.publish_from_db(
                    workspace=resource.workspace,
                    store_name=resource.store_name,
                    layer_name=resource.layer_name,
                    layer_title=resource.layer_title,
                    datatype=resource.datatype_id,
                    start_time=resource.start,
                )
            all_pubstatus.extend(pubstatuses)
        return all_pubstatus

    def delete(self, resources: List[GeoserverResource], resourcelayercount: Dict[str, int]):
        rlc_copy = {k: v for k, v in resourcelayercount.items()}
        for resource in resources:
            self.driver.delete_layer(
                workspace=resource.workspace,
                layer_name=resource.layer_name,
                store_name=resource.store_name,
                is_coveragestore=resource.storage_location is not None and rlc_copy[resource.resource_id] == 1,
            )
            rlc_copy[resource.resource_id] -= 1
