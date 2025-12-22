import json
import threading
import time
from ssl import SSLContext, PROTOCOL_TLSv1_2
from typing import Dict, Callable
import pika
from pika.exceptions import AMQPConnectionError

from cat import log, hook
from cat.utils import pod_id


_march_hare = None
_consumer_threads = []

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


class MarchHare:
    def __init__(self, host: str, port: int, username: str, password: str, is_tls: bool = False):
        self._connection_parameters = None
        self.pod_id = pod_id()

        parameters = pika.ConnectionParameters(
            host=host,
            port=port,
            credentials=pika.PlainCredentials(
                username=username,
                password=password,
            )
        )

        if is_tls:
            # SSL Context for TLS configuration of Amazon MQ for RabbitMQ
            ssl_context = SSLContext(PROTOCOL_TLSv1_2)
            ssl_context.set_ciphers("ECDHE+AESGCM:!ECDSA")

            parameters.ssl_options = pika.SSLOptions(context=ssl_context)

        self._connection_parameters = parameters

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

            channel.exchange_declare(exchange=exchange, exchange_type=exchange_type)

            event = {
                "event_type": event_type,
                "payload": payload,
                "source_pod": self.pod_id,
            }
            message = json.dumps(event)

            channel.basic_publish(
                exchange=exchange,
                routing_key="",
                body=message
            )
            log.debug(f"Event {event_type} sent to exchange {exchange} with payload: {payload}")
        except AMQPConnectionError as e:
            log.error(f"Connection error to RabbitMQ: {e}")
        finally:
            if connection:
                connection.close()

    def consume_event(self, callback: Callable, exchange: str, exchange_type: str = "fanout"):
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


def _consume_plugin_events(lizard):
    """
    Consumer thread that listens for activation events from RabbitMQ.
    """
    global _march_hare, _consumer_threads

    _pod_id = pod_id()

    def callback(ch, method, properties, body):
        """Handle the received message."""
        try:
            event = json.loads(body)

            if event.get("source_pod") == _pod_id:
                log.debug(f"Ignoring event with payload {event['payload']} from the same pod {_pod_id}")
                return

            if event["event_type"] == MarchHareConfig.events["PLUGIN_INSTALLATION"]:
                payload = event["payload"]
                lizard.plugin_manager.install_extracted_plugin(payload["plugin_id"], payload["plugin_path"])
            elif event["event_type"] == MarchHareConfig.events["PLUGIN_UNINSTALLATION"]:
                payload = event["payload"]
                lizard.plugin_manager.uninstall_plugin(payload["plugin_id"])
            else:
                log.warning(f"Unknown event type: {event['event_type']}. Message body: {body}")
        except json.JSONDecodeError as e:
            log.error(f"Failed to decode JSON message: {e}. Message body: {body}")
        except Exception as e:
            log.error(f"Error processing message: {e}. Message body: {body}")

    _march_hare.consume_event(callback, MarchHareConfig.channels["PLUGIN_EVENTS"])


def _start_consumer_threads(lizard):
    global _consumer_threads
    _consumer_threads = [
        threading.Thread(target=_consume_plugin_events, args=(lizard,), daemon=True)
    ]
    for thread in _consumer_threads:
        thread.start()


def _end_consumer_threads():
    global _consumer_threads

    for thread in _consumer_threads:
        if thread.is_alive():
            thread.join(timeout=1)
    _consumer_threads = []


@hook(priority=0)
def before_lizard_bootstrap(lizard) -> None:
    global _march_hare, _consumer_threads

    settings = lizard.plugin_manager.get_plugin().load_settings()
    if settings["is_disabled"]:
        return

    _march_hare = MarchHare(
        host=settings["host"],
        port=settings["port"],
        username=settings["username"],
        password=settings["password"],
        is_tls=settings["is_tls"],
    )

    _start_consumer_threads(lizard)


@hook(priority=0)
def before_lizard_shutdown(lizard) -> None:
    global _march_hare, _consumer_threads

    _end_consumer_threads()
    _march_hare = None


@hook(priority=0)
def lizard_notify_plugin_installation(plugin_id: str, plugin_path: str, lizard) -> None:
    global _march_hare

    if _march_hare is None:
        return

    _march_hare.notify_event(
        event_type=MarchHareConfig.events["PLUGIN_INSTALLATION"],
        payload={
            "plugin_id": plugin_id,
            "plugin_path": plugin_path
        },
        exchange=MarchHareConfig.channels["PLUGIN_EVENTS"],
    )


@hook(priority=0)
def lizard_notify_plugin_uninstallation(plugin_id, lizard) -> None:
    global _march_hare

    if _march_hare is None:
        return

    _march_hare.notify_event(
        event_type=MarchHareConfig.events["PLUGIN_UNINSTALLATION"],
        payload={"plugin_id": plugin_id},
        exchange=MarchHareConfig.channels["PLUGIN_EVENTS"],
    )
