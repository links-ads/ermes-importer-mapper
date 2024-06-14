import logging
import time
from typing import List

from importer.database.schemas import GeoserverResourceSchema
from importer.driver.rabbitmq_driver import (
    BasicProducer,
    Consumer,
    DeliveryMode,
    JsonEncoder,
    ReconnectingConsumer,
)
from importer.dto.layer_publication_status import LayerPublicationStatus
from importer.settings.instance import settings

LOG = logging.getLogger(__name__)


class MessageBusManager:
    def __init__(self):
        self.broker_host = settings.rabbitmq_host
        self.broker_port = settings.rabbitmq_port
        self.broker_user = settings.rabbitmq_user
        self.broker_pass = settings.rabbitmq_pass
        self.ca_cert_file = settings.rabbitmq_ca_cert_file
        self.cert_file = settings.rabbitmq_cert_file
        self.key_file = settings.rabbitmq_key_file
        self.broker_vhost = settings.rabbitmq_vhost
        self.consumer_routing = settings.get_rabbitmq_consumer_routing()

        self.encoder = JsonEncoder()
        self.delivery_mode = DeliveryMode.PERSISTENT.value
        self.consumer = None

    def __del__(self):
        self.disconnect()

    def get_consumer(self, callback):
        rabbitmq_consumer = Consumer(
            self.broker_host,
            self.broker_port,
            self.ca_cert_file,
            self.cert_file,
            self.key_file,
            self.broker_vhost,
            callback
        )
        rabbitmq_reconnecting_consumer = ReconnectingConsumer(rabbitmq_consumer, self.consumer_routing)
        return rabbitmq_reconnecting_consumer

    def consume(self, callback):
        if self.consumer is None:
            self.consumer = self.get_consumer(callback)
        self.consumer.run()

    def disconnect(self):
        if self.consumer:
            self.consumer.stop()

    def publication_report(
        self, resources: List[GeoserverResourceSchema], all_pubstatus: List[LayerPublicationStatus]
    ):
        resource_dict = {}

        for resource in resources:
            resource_dict[resource.layer_name] = resource

        rabbit_producer = None
        previous_reqcode = None

        for pubstatus in all_pubstatus:
            if not pubstatus.is_layer:
                continue

            resource = resource_dict[pubstatus.original_name]
            body = {
                "datatype_id": pubstatus.datatype,
                "status_code": 200 if pubstatus.success else 500,
                "name": f"{resource.workspace}:{pubstatus.layer_name}",
                "message": "Layers imported successfully" if pubstatus.success else pubstatus.exception,
                "type": "layer",
                "urls": [],
                "metadata": {},
            }

            try:
                if rabbit_producer is None or previous_reqcode != resource.request_code:
                    previous_reqcode = resource.request_code
                    if rabbit_producer is not None:
                        rabbit_producer.disconnect()

                    properties = {
                        "delivery_mode": self.delivery_mode,
                        "app_id": "imp",
                        "user_id": settings.rabbitmq_user,
                        "timestamp": int(time.time()),
                    }

                    queue_suffix = f".{pubstatus.datatype}"
                    if resource.request_code:
                        queue_suffix += f".{resource.request_code}"
                        properties["message_id"] = resource.request_code.split(".")[-1]

                    rabbit_producer = BasicProducer(
                        self.broker_host,
                        self.broker_port,
                        self.ca_cert_file,
                        self.cert_file,
                        self.key_file,
                        self.broker_vhost,
                        settings.get_rabbitmq_producer_routing(queue_suffix),
                        self.encoder,
                        properties=properties,
                    )

                    rabbit_producer.connect()

                rabbit_producer.publish(body)
            except Exception as e:
                LOG.exception(e)

        try:
            if rabbit_producer is not None:
                rabbit_producer.disconnect()
        except Exception as e:
            LOG.exception(e)
