import json
import redis
import threading
import time
from typing import Dict, Callable

from cat import log, hook
from cat.db.database import get_db
from cat.utils import pod_id

# Max messages to keep in the stream to prevent memory explosion
STREAM_MAX_LEN = 1000


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
    def __init__(self):
        self.pod_id = pod_id()
        self._redis_client = get_db()

    def notify_event(self, event_type: str, payload: Dict, stream_name: str):
        """
        Publish an event to Redis Stream.
        """
        try:
            event = {
                "event_type": event_type,
                "payload": json.dumps(payload),
                "source_pod": self.pod_id,
            }

            # XADD with approximate trimming (~ operator) for performance
            self._redis_client.xadd(
                name=stream_name,
                fields=event,
                maxlen=MarchHareConfig.STREAM_MAX_LEN,
                approximate=True
            )

            log.debug(f"Event {event_type} sent to stream {stream_name}")
        except Exception as e:
            log.error(f"Error publishing to Redis: {e}")

    def consume_event(self, callback: Callable, stream_name: str):
        """
        Read new messages from the stream starting from 'now'.
        """
        # '$' tells Redis to only return messages that arrive after we start reading
        last_id = '$'

        log.debug(f"[*] Started Redis Stream consumer on {stream_name}. Waiting for events...")

        while True:
            try:
                # XREAD blocks for 1 second (1000ms) waiting for new data
                events = self._redis_client.xread({stream_name: last_id}, count=1, block=1000)

                for stream, messages in events:
                    for message_id, data in messages:
                        # Process message
                        callback(data)
                        # Update last_id to the one we just processed to move the cursor forward
                        last_id = message_id

            except redis.ConnectionError as e:
                log.warning(f"Redis connection lost: {e}. Retrying in 5 seconds...")
                time.sleep(5)
            except Exception as e:
                log.error(f"Error in Redis consumer loop: {e}")
                time.sleep(1)


_march_hare: MarchHare | None = None
_consumer_threads = []


def _consume_plugin_events(lizard):
    """
    Consumer thread that listens for activation events from RabbitMQ.
    """
    global _march_hare

    _pod_id = pod_id()

    def callback(data):
        """Handle the received message."""
        try:
            # Redis Stream fields are key-value pairs
            event_type = data.get("event_type")
            source_pod = data.get("source_pod")
            payload = json.loads(data.get("payload", "{}"))

            if source_pod == _pod_id:
                return

            if event_type == MarchHareConfig.events["PLUGIN_INSTALLATION"]:
                lizard.plugin_manager.install_extracted_plugin(payload["plugin_id"])
                lizard.activate_plugin_endpoints(payload["plugin_id"])
                return

            if event_type == MarchHareConfig.events["PLUGIN_UNINSTALLATION"]:
                lizard.plugin_manager.uninstall_plugin(payload["plugin_id"], dispatch_event=False)
                return

            log.warning(f"Unknown event type: {event_type}")
        except Exception as e:
            log.error(f"Error processing Redis message: {e}")

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
    global _march_hare
    settings = lizard.plugin_manager.get_plugin().load_settings()
    if settings["is_disabled"]:
        return

    _march_hare = MarchHare()
    _start_consumer_threads(lizard)


@hook(priority=0)
def before_lizard_shutdown(lizard) -> None:
    global _march_hare

    _end_consumer_threads()
    _march_hare = None


@hook(priority=999)
def lizard_notify_plugin_installation(plugin_id: str, plugin_path: str, lizard) -> None:
    global _march_hare

    if _march_hare is None:
        return

    if plugin_id and lizard.plugin_manager.plugins.get(plugin_id):
        _march_hare.notify_event(
            event_type=MarchHareConfig.events["PLUGIN_INSTALLATION"],
            payload={
                "plugin_id": plugin_id,
                "plugin_path": plugin_path
            },
            stream_name=MarchHareConfig.channels["PLUGIN_EVENTS"],
        )


@hook(priority=0)
def lizard_notify_plugin_uninstallation(plugin_id, lizard) -> None:
    global _march_hare

    if _march_hare is None:
        return

    if lizard.plugin_manager.plugins.get(plugin_id) is None:
        _march_hare.notify_event(
            event_type=MarchHareConfig.events["PLUGIN_UNINSTALLATION"],
            payload={"plugin_id": plugin_id},
            stream_name=MarchHareConfig.channels["PLUGIN_EVENTS"],
        )
