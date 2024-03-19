import logging
from datetime import datetime, timedelta
from typing import List

from importer.database.extensions import db_session
from importer.database.models import GeoserverResource
from importer.database.schemas import MessageSchema
from importer.manager.data_retrieval_manager import DataRetrievalManager
from importer.manager.data_storage_manager import DataStorageManager
from importer.manager.geoserver_manager import GeoserverManager
from importer.manager.message_bus_manager import MessageBusManager
from importer.settings.instance import settings

LOG_FORMAT = "%(levelname) -10s %(asctime)s %(name) -30s %(funcName) -35s %(lineno) -5d: %(message)s"
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)
LOG = logging.getLogger(__name__)

data_retrieval_manager = DataRetrievalManager()
data_storage_manager = DataStorageManager()
geoserver_manager = GeoserverManager()


def main():
    def check_message(message):
        errors = []
        message_schema = MessageSchema(**message)
        # if error_condition:
        #    errors.append('Error message')
        return message_schema, errors

    def callback(message, basic_deliver, properties):
        try:
            project_name = properties.headers.get("project")
        except (KeyError, TypeError, AttributeError):
            LOG.info("No project info found in notification, setting default project name")
            project_name = settings.geoserver_workspace
        try:
            message_schema, errors = check_message(message)
            if len(errors) > 0:
                for error in errors:
                    LOG.error(error)
                return
            LOG.info(message_schema.type)
            if message_schema.type in ["delete", "update"]:
                with db_session() as session:
                    resources = data_storage_manager.get_resources(
                        session=session, workspace=project_name, resource_id=message_schema.id
                    )
                    LOG.info(resources)
                    reslayercount = data_storage_manager.countlayers_perresource(session=session, resources=resources)
                    geoserver_manager.delete(resources=resources, resourcelayercount=reslayercount)
                    data_storage_manager.delete_resources(session, resources, resourcelayercount=reslayercount)
            if message_schema.type in ["create", "update"]:
                data_list = data_retrieval_manager.download_data(project_name, message_schema=message_schema)
                saved_resources = data_storage_manager.save_resources(data_list=data_list)
                publication_status = geoserver_manager.publish(resources=saved_resources)
                data_storage_manager.add_resources_entries(saved_resources, publication_status)
                message_bus_manager.publication_report(saved_resources, publication_status)
                impacted_datatypes = list(set(ps.datatype for ps in publication_status if ps.success))
                delete_oldest_resources(workspace=project_name, datatypes=impacted_datatypes)
        except Exception as e:
            LOG.error(e, exc_info=True)

    def delete_oldest_resources(workspace: str, datatypes: List[str] = None):
        with db_session() as session:
            expired_resources = []
            for dtype in datatypes:

                try:
                    delete_after_days = data_storage_manager.get_layer_settings(
                        session, project=workspace, datatype_id=dtype
                    ).delete_after_days
                except AttributeError:
                    delete_after_days = None

                try:
                    delete_after_count = data_storage_manager.get_layer_settings(
                        session, project=workspace, datatype_id=dtype
                    ).delete_after_count
                except Exception:
                    delete_after_count = None

                resources = data_storage_manager.get_resources(
                    session=session, workspace=workspace, datatype_ids=[dtype], expire_on=datetime.utcnow()
                )
                expired_resources.extend(resources)

                if delete_after_days and delete_after_days > 0:
                    resources = data_storage_manager.get_resources(
                        session=session,
                        workspace=workspace,
                        datatype_ids=[dtype],
                        created_before=(datetime.utcnow() - timedelta(days=delete_after_days)),
                    )
                    expired_resources.extend(resources)

                if delete_after_count and delete_after_count > 0:
                    resources = data_storage_manager.get_resources(
                        session=session,
                        workspace=workspace,
                        datatype_ids=[dtype],
                        order_by=GeoserverResource.created_at,
                    )
                    expired_resources.extend(resources[:-delete_after_count])

            LOG.info(
                f"Expired resources to delete (datatype {datatypes}): {[r.resource_id for r in expired_resources]}"
            )
            reslayercount = data_storage_manager.countlayers_perresource(session=session, resources=expired_resources)
            geoserver_manager.delete(resources=expired_resources, resourcelayercount=reslayercount)
            data_storage_manager.delete_resources(session, expired_resources, resourcelayercount=reslayercount)

    message_bus_manager = MessageBusManager()
    message_bus_manager.consume(callback=callback)


if __name__ == "__main__":
    main()
