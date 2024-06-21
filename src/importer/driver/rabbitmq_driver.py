import json
import logging
import ssl
import time
import os
from enum import Enum
from socket import gaierror

import pika
from pika.exceptions import StreamLostError

LOG = logging.getLogger(__name__)


class DeliveryMode(Enum):
    TRANSIENT = 1
    PERSISTENT = 2


class Encoder:
    """
    Simple abstract class defining an encoder interface
    """

    abstract = True

    def __init__(self, content_type, encoding):
        """
        Initializes the encoder setting which content type should work with
        :param content_type:    standard network parameter
        """
        self.content_type = content_type
        self.encoding = encoding

    def encode(self, message):
        """
        Abstract implementation, should be extended in subclass.
        :param message: content to send
        :return:        None
        """
        raise NotImplementedError("Abstract method: inherit Encoder and provide an implementation")


class JsonEncoder(Encoder):
    """
    JSON implementation of the encoder interface
    """

    def __init__(self, schema=json):
        """
        Initializes the encoder setting a default app/json content type
        """
        super(JsonEncoder, self).__init__(content_type="application/json", encoding="utf-8")  # noqa: UP008
        self._schema = schema

    def encode(self, message):
        """
        Serializes the content of message as json
        :param message: message to be sent
        :return:        json string
        """
        return self._schema.dumps(message)


class BasicProducer:

    def __init__(self, host, port, ca_cert_file, cert_file, key_file, vhost, routing, encoder, use_ssl=True, properties={}):
        """
        Creates a new RabbitMQ client able to publish messages onto a specific exchange.
        :param host, port, user, password:     amqp broker infos
        :param routing: routing definitions (exchange, type etc.)
        :param encoder: encoder abstraction, providing a serialization method and other info
        :param delivery_mode:   transient or persistent
        """
        self.host = host
        self.ca_cert_file = ca_cert_file
        self.cert_file = cert_file
        self.key_file = key_file
        
        credentials = pika.credentials.ExternalCredentials()
        ssl_options = self.__get_tls_parameters()
        
        self._connection_parameters = pika.ConnectionParameters(
                credentials=credentials,
                host=self.host,
                port=port,
                virtual_host=vhost,
                ssl_options=ssl_options,
            )
        self._connection = None
        self._channel = None
        self.exchange = routing.get("exchange")
        self.exchange_type = routing.get("exchange_type")
        self.routing_key = routing.get("routing_key")
        self._encoder = encoder
        self._properties = pika.BasicProperties(
            content_type=self._encoder.content_type, content_encoding=self._encoder.encoding, **properties
        )


    def __get_tls_parameters(self):
        assert os.path.exists(self.ca_cert_file), f"CA certificate file not found: {self.ca_cert_file}"
        assert os.path.exists(self.cert_file), f"Client certificate file not found: {self.cert_file}"
        assert os.path.exists(self.key_file), f"Client key file not found: {self.key_file}"
        context = ssl.create_default_context(cafile=self.ca_cert_file)
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(
            certfile=self.cert_file,
            keyfile=self.key_file,
        )
        return pika.SSLOptions(context, server_hostname=self.host)

    def __del__(self):
        self.disconnect()

    def connect(self):
        """
        Connects the current client to a RabbitMQ broker, using a simple blocking connection.
        :return:    None
        """

        if self._connection is None or self._connection.is_closed:
            LOG.debug("Publisher connecting to RabbitMQ")

            self._connection = pika.BlockingConnection(parameters=self._connection_parameters)
            self._channel = self._connection.channel()
            self._channel.exchange_declare(
                exchange=self.exchange, exchange_type=self.exchange_type, durable=True, passive=True
            )

    def publish(self, message):
        """
        Publishes a new message on the exchange specified during init.
        :param message: message to be sent
        :return:        None
        """
        LOG.debug("Publishing message: %s", message)
        body = self._encoder.encode(message)
        self._channel.basic_publish(self.exchange, self.routing_key, body, self._properties)

    def disconnect(self):
        """
        Disconnects the client, if the connection is not None.
        :return:    None
        """
        LOG.debug("Publisher disconnecting from RabbitMQ")
        if self._connection and self._connection.is_open:
            try:
                self._connection.close()
            except StreamLostError:
                pass
        self._connection = None


class ReconnectingProducer:
    """Producer that will reconnect if the nested worker indicates that a reconnect is necessary."""

    def __init__(self, producer):
        """
        Initializes a reconnecting consumer.
        :param consumer:    async rabbitmq consumer
        :param config:      app config
        """
        self._reconnect_delay = 0
        self._producer = producer
        self._reconnect = True

    def connect(self):
        while True:
            try:
                self._producer.connect()
                break
            except (pika.exceptions.ConnectionClosed, gaierror, StreamLostError, BrokenPipeError):
                self._maybe_reconnect()

    def publish(self, message):
        """
        Publish message, reconnecting if necessary
        :return:    None
        """
        while True:
            try:
                self._producer.publish(message)
                self._reconnect_delay = 0
                break
            except (pika.exceptions.ConnectionClosed, gaierror, StreamLostError, BrokenPipeError):
                self._maybe_reconnect(was_publishing=True)

    def _maybe_reconnect(self, was_publishing=False):
        """
        Tries to reconnect the underlying consumer instance.
        :return:    None
        """
        reconnect_delay = self._get_reconnect_delay()
        LOG.debug("Reconnecting Prodcer after %d seconds", reconnect_delay)
        time.sleep(reconnect_delay)
        self._producer.disconnect()
        if was_publishing:
            self.connect()

    def _get_reconnect_delay(self):
        """
        Reconnection delay computation using exponential back-off.
        :return:    reconnection delay in seconds
        """
        self._reconnect_delay += 1
        if self._reconnect_delay > 30:
            self._reconnect_delay = 30
        return self._reconnect_delay

    def disconnect(self):
        self._producer.disconnect()


class Consumer:
    """This is an example consumer that will handle unexpected interactions with RabbitMQ such as channel and
    connection closures. If RabbitMQ closes the connection, this class will stop and indicate that reconnection is
    necessary. You should look at the output, as there are limited reasons why the connection may be closed,
    which usually are tied to permission related issues or socket timeouts. If the channel is closed,
    it will indicate a problem with one of the commands that were issued and that should surface in the output as well.
    """

    def __init__(
        self,
        host,
        port,
        ca_cert_file,
        cert_file,
        key_file,
        vhost,
        callback,
        schema=json,
        prefetch=1,
        ack_every=1,
        passive=True,
        use_ssl=True,
    ):
        """Create a new instance of the consumer class, passing in the AMQP URL used to connect to RabbitMQ.
        :param str amqp_url: The AMQP url to connect with
        :param fun callback: function to call on message received
        :param int prefetch: number of messages to prefetch
        """
        self.host = host
        self.ca_cert_file = ca_cert_file
        self.cert_file = cert_file
        self.key_file = key_file
        
        credentials = pika.credentials.ExternalCredentials()
        ssl_options = self.__get_tls_parameters()
        
        self._connection_parameters = pika.ConnectionParameters(
                credentials=credentials,
                host=self.host,
                port=port,
                virtual_host=vhost,
                ssl_options=ssl_options,
            )
        
        self._callback = callback
        self._schema = schema
        self.should_reconnect = False
        self.was_consuming = False
        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._consuming = False
        # update the configuration from dictionary
        self.exchange = None
        self.exchange_type = None
        self.queue = None
        self.routing_key = None
        # In production, experiment with higher prefetch values
        # for higher consumer throughput
        self._prefetch_count = prefetch
        self._passive = passive
        self._ack_every = ack_every
        self._received = 0
        self._ready = False
        
    def __get_tls_parameters(self):
        context = ssl.create_default_context(cafile=self.ca_cert_file)
        context.verify_mode = ssl.CERT_REQUIRED
        context.load_cert_chain(
            certfile=self.cert_file,
            keyfile=self.key_file,
        )
        return pika.SSLOptions(context, server_hostname=self.host)

    def configure(self, config):
        """Resets the worker instance to the default parameters.
        This is essentially a public init function, so that the worker can be restarted.
        :param dict config: dictionary containing routing information
        """
        self.should_reconnect = False
        self.was_consuming = False
        self._connection = None
        self._channel = None
        self._closing = False
        self._consumer_tag = None
        self._consuming = False
        # update the configuration from dictionary
        self.exchange = config.get("exchange", self.exchange)
        self.exchange_type = config.get("exchange_type", self.exchange_type)
        self.queue = config.get("queue", self.queue)
        self.routing_key = config.get("routing_key", self.routing_key)
        # In production, experiment with higher prefetch values
        # for higher consumer throughput
        self._received = 0
        self._ready = True

    def connect(self):
        """Connects to RabbitMQ, returning the connection handle.
        When the connection is established, the on_connection_open method will be invoked.
        If the connection fails, the on_connection_open_error method will be invoked.
        When closed, the last callback on_connection_closed will be executed.
        :rtype: pika.SelectConnection
        """
        if not self._ready:
            raise AssertionError()
        LOG.info("Connecting to %s", self._connection_parameters)
        return pika.SelectConnection(
            parameters=self._connection_parameters,
            on_open_callback=self.on_connection_open,
            on_open_error_callback=self.on_connection_open_error,
            on_close_callback=self.on_connection_closed,
        )

    def close_connection(self):
        """Closes the connection with RabbitMQ, preventing multiple calls."""
        self._consuming = False
        if self._connection.is_closing or self._connection.is_closed:
            LOG.debug("Connection is closing or already closed")
        else:
            LOG.debug("Closing connection")
            self._connection.close()

    def on_connection_open(self, _unused_connection):
        """Callback invoked once the connection to RabbitMQ has been established.
        Opens a new channel setting a new callback to continue the flow.
        :param SelectConnection _unused_connection: The connection handle, if needed
        """
        LOG.debug("Connection opened")
        self._connection.channel(on_open_callback=self.on_channel_open)

    def on_connection_open_error(self, _unused_connection, err):
        """This method is called by pika if the connection to RabbitMQ can't be established.
        :param pika.SelectConnection _unused_connection: The connection
        :param Exception err: The error
        """
        LOG.error("Connection open failed: %s", str(err))
        self.reconnect()

    def on_connection_closed(self, _unused_connection, reason):
        """This method is invoked by pika when the connection to RabbitMQ is
        closed unexpectedly. Since it is unexpected, we will reconnect to
        RabbitMQ if it disconnects.
        :param pika.connection.Connection _unused_connection: The closed connection obj
        :param Exception reason: exception representing reason for loss of
            connection.
        """
        self._channel = None
        if self._closing:
            self._connection.ioloop.stop()
        else:
            LOG.warning("Connection closed, reconnect necessary: %s", reason)
            self.reconnect()

    def reconnect(self):
        """Will be invoked if the connection can't be opened or is closed.
        Indicates that a reconnect is necessary then stops the ioloop.
        """
        self.should_reconnect = True
        self.stop()

    def on_channel_open(self, channel):
        """Invoked when the channel has been opened. Sets the callback for channel closed and the exchange setup.
        :param pika.channel.Channel channel: The channel object
        """
        LOG.debug("Channel opened")
        self._channel = channel
        self._channel.add_on_close_callback(self.on_channel_closed)
        LOG.debug("Declaring exchange: %s", self.exchange)
        self._channel.exchange_declare(
            exchange=self.exchange,
            exchange_type=self.exchange_type,
            passive=self._passive,
            callback=self.on_exchange_declared,
        )

    def on_channel_closed(self, channel, reason):
        """Invoked by pika when RabbitMQ unexpectedly closes the channel.
        Channels are usually closed when something violates the protocol,
        such as re-declare an exchange or queue with different parameters.
        In this case, the connection is closed to shutdown the object.
        :param Channel channel: The closed channel
        :param Exception reason: why the channel was closed
        """
        LOG.warning("Channel %i was closed: %s", channel, reason)
        self.close_connection()

    def on_exchange_declared(self, _unused_frame):
        """Invoked when RabbitMQ has finished the Exchange.Declare RPC command.
        Once the exchange is ready, the method declares the specified queue.
        :param Method _unused_frame: Exchange.DeclareOk response frame
        """
        LOG.debug("Exchange declared: %s", self.exchange)
        LOG.debug("Declaring queue %s", self.queue)
        self._channel.queue_declare(queue=self.queue, callback=self.on_queue_declared, passive=self._passive)

    def on_queue_declared(self, _unused_frame):
        """Method invoked when the queue setup has completed. This method binds the queue
        and exchange together with the routing key by issuing the Queue.Bind.
        When this command is complete, the on_bind method will be invoked by pika.
        :param pika.frame.Method _unused_frame: The Queue.DeclareOk frame
        """
        LOG.debug("Binding %s to %s with %s", self.exchange, self.queue, self.routing_key)
        if not self._passive:
            self._channel.queue_bind(self.queue, self.exchange, routing_key=self.routing_key, callback=self.on_bind)
        else:
            self.on_bind(_unused_frame)

    def on_bind(self, _unused_frame):
        """Invoked when the Queue.Bind method has completed. Sets the prefetch count for the channel.
        :param pika.frame.Method _unused_frame: The Queue.BindOk response frame
        """
        LOG.debug("Queue bound: %s", self.queue)
        self._channel.basic_qos(prefetch_count=self._prefetch_count, callback=self.on_qos_done)

    def on_qos_done(self, _unused_frame):
        """Invoked when the Basic.QoS method has completed. Starts consuming messages by calling start_consuming.
        :param pika.frame.Method _unused_frame: The Basic.QosOk response frame
        """
        LOG.debug("QOS set to: %d", self._prefetch_count)
        self.start_consuming()

    def start_consuming(self):
        """Sets up the consumer by first calling add_on_cancel_callback so that the object is notified if RabbitMQ
        cancels the consumer. It then issues the basic_consume command which returns the consumer tag that
        uniquely identifies the consumer. This is useful to cancel the consumer.
        The on_message callback will invoke when a message is fully received.
        """
        LOG.debug("Issuing consumer related RPC commands")
        LOG.debug("Adding consumer cancellation callback")
        self._channel.add_on_cancel_callback(self.on_consumer_cancelled)
        self._consumer_tag = self._channel.basic_consume(self.queue, self.on_message)
        self.was_consuming = True
        self._consuming = True

    def on_consumer_cancelled(self, method_frame):
        """Invoked when RabbitMQ sends a Basic.Cancel for a consumer receiving messages.
        :param pika.frame.Method method_frame: The Basic.Cancel frame
        """
        LOG.debug("Consumer was cancelled remotely, shutting down: %r", method_frame)
        if self._channel:
            self._channel.close()

    def on_message(self, _unused_channel, basic_deliver, properties, body):
        """Invoked by pika when a message is delivered.
        :param pika.channel.Channel _unused_channel: The channel object, unused in this case
        :param Deliver basic_deliver: object carrying the exchange, routing key, delivery tag and redelivered flag
        :param BasicProperties properties: properties containing the message props
        :param bytes body: The message body
        """
        LOG.debug("Received message # %s from %s", basic_deliver.delivery_tag, properties.app_id)
        self._received = (self._received + 1) % self._ack_every
        try:
            message = self._schema.loads(body)
            if isinstance(message, dict):
                message_as_dict = message
            else:
                message_as_dict = self._schema.loads(message)
            LOG.debug(message)
        except (json.decoder.JSONDecodeError, TypeError) as e:
            LOG.warning(f"Map Request message is in wrong format - {str(e)}")
            message_as_dict = body
            # raise
        self._callback(message_as_dict, basic_deliver, properties)
        if self._received == 0:
            LOG.debug("Sending ack")
            self._channel.basic_ack(basic_deliver.delivery_tag, multiple=True)

    def stop_consuming(self):
        """Tells RabbitMQ to stop consuming by sending the Basic.Cancel RPC command."""
        if self._channel:
            LOG.debug("Sending a Basic.Cancel RPC command to RabbitMQ")
            self._channel.basic_cancel(self._consumer_tag, self.on_canceled)

    def on_canceled(self, _unused_frame):
        """Invoked when RabbitMQ acknowledges the cancellation of a consumer.
        Closes the channel, which will first invoke the on_channel_closed method once the channel
        has been closed, then in-turn close the connection.
        :param pika.frame.Method _unused_frame: The Basic.CancelOk frame
        """
        self._consuming = False
        LOG.debug("RabbitMQ acknowledged the cancellation of the consumer: %s", self._consumer_tag)
        LOG.debug("Closing the channel")
        self._channel.close()

    def run(self):
        """Runs the example consumer by connecting to RabbitMQ and then
        starting the IOLoop to block and allow the SelectConnection to operate.
        """
        LOG.info("Starting consumer")
        self._connection = self.connect()
        LOG.info("Consumer connected. Starting consuming")
        self._connection.ioloop.start()

    def stop(self):
        """Cleanly shutdown the connection to RabbitMQ by stopping the consumer. On_canceled will be invoked and will
        close the channel and connection. The IOLoop is started again because this method is invoked when CTRL-C is
        pressed raising a KeyboardInterrupt exception. This exception stops the IOLoop which needs to be running for
        pika to communicate with RabbitMQ. All of the commands issued prior to starting the IOLoop will be buffered
        but not processed.
        """
        if not self._closing and self._connection:
            self._closing = True
            LOG.debug("Stopping consumer")
            if self._consuming:
                self.stop_consuming()
            self._connection.ioloop.stop()
            LOG.debug("Consumer stopped")


class ReconnectingConsumer:
    """Consumer that will reconnect if the nested worker indicates that a reconnect is necessary."""

    def __init__(self, consumer, config):
        """
        Initializes a reconnecting consumer.
        :param consumer:    async rabbitmq consumer
        :param config:      app config
        """
        self._reconnect_delay = 0
        self._consumer = consumer
        self._config = config
        self._consumer.configure(config)
        self._reconnect = True

    def run(self):
        """
        Starts an async loop, interrupting on SIGINT
        :return:    None
        """
        while True:
            try:
                self._consumer.run()
            except KeyboardInterrupt:
                self._consumer.stop()
                break
            if not self._reconnect:
                break
            self._maybe_reconnect()

    def _maybe_reconnect(self):
        """
        Tries to reconnect the underlying consumer instance.
        :return:    None
        """
        if self._consumer.should_reconnect:
            self._consumer.stop()
            reconnect_delay = self._get_reconnect_delay()
            LOG.debug("Reconnecting Consumer after %d seconds", reconnect_delay)
            time.sleep(reconnect_delay)
            self._consumer.configure(self._config)

    def _get_reconnect_delay(self):
        """
        Reconnection delay computation using exponential back-off.
        :return:    reconnection delay in seconds
        """
        if self._consumer.was_consuming:
            self._reconnect_delay = 0
        else:
            self._reconnect_delay += 1
        if self._reconnect_delay > 30:
            self._reconnect_delay = 30
        return self._reconnect_delay

    def stop(self):
        self._consumer.stop()
        self._reconnect = False
