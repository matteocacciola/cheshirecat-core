import time
from os import getenv
from typing import Dict
import pika
import json
from pika.exceptions import AMQPConnectionError

from cat.log import log
from cat.utils import singleton


class MarchHareConfig:
    # List of channels for event management
    channels = {
        "PLUGIN_EVENTS": "plugin_events"
    }

    # list of event types for plugin management
    events = {
        "PLUGIN_INSTALLATION": "plugin_installation",
        "PLUGIN_UNINSTALLATION": "plugin_uninstallation",
    }

    is_enabled = getenv("CCAT_RABBITMQ_HOST") is not None


@singleton
class MarchHare:
    def __init__(self):
        self._connection_parameters = None
        if MarchHareConfig.is_enabled:
            self._connection_parameters = pika.ConnectionParameters(
                host=getenv("CCAT_RABBITMQ_HOST"),
                port=int(getenv("CCAT_RABBITMQ_PORT")),
                credentials=pika.PlainCredentials(
                    username=getenv("CCAT_RABBITMQ_USER"),
                    password=getenv("CCAT_RABBITMQ_PASSWORD")
                )
            )

    def notify_event(self, event_type: str, payload: Dict, exchange: str, exchange_type: str = "fanout"):
        """
        Publish an event to RabbitMQ.

        Args:
            event_type (str): The type of the event to be sent.
            payload (Dict): The payload of the event to be sent.
            exchange (str): The name of the exchange to publish the event to.
            exchange_type (str): The type of the exchange to use. Defaults to "fanout".
        """
        if self._connection_parameters is None:
            return

        connection = None
        try:
            connection = pika.BlockingConnection(self._connection_parameters)
            channel = connection.channel()

            channel.exchange_declare(exchange=event_type, exchange_type=exchange_type)

            event = {"event_type": event_type, "payload": payload}
            message = json.dumps(event)

            channel.basic_publish(
                exchange=exchange,
                routing_key="",
                body=message
            )
            log.debug(f"Event {event_type} sent to exhange {exchange} with payload: {payload}")
        except AMQPConnectionError as e:
            log.error(f"Connection error to RabbitMQ: {e}")
        finally:
            if connection:
                connection.close()

    def consume_event(self, callback: callable, exchange: str, exchange_type: str = "fanout"):
        if self._connection_parameters is None:
            return

        connection = None
        while True:
            try:
                connection = pika.BlockingConnection(self._connection_parameters)
                channel = connection.channel()

                channel.exchange_declare(exchange=exchange, exchange_type=exchange_type)

                # create a temporary and anonymous queue
                # "exclusive=True" means the queue will be deleted when the consumer disconnects.
                # This ensures that each node has its own queue and receives all messages.
                result = channel.queue_declare(queue="", exclusive=True)
                queue_name = result.method.queue

                # Link the queue to the `exchange` exchange
                channel.queue_bind(exchange=exchange, queue=queue_name)

                log.debug('[*] Waiting for events. Press CTRL+C to exit.')

                channel.basic_consume(queue=queue_name, on_message_callback=callback, auto_ack=True)
                channel.start_consuming()
            except pika.exceptions.AMQPConnectionError as e:
                log.warning(f"Connection error to RabbitMQ: {e}. Retrying in 5 seconds...")
                time.sleep(5)
            finally:
                if connection:
                    connection.close()
