import json
import random
import redis
import threading
import time
from typing import Dict, Callable, Optional

from cat import log, hook
from cat.db.database import get_db
from cat.utils import pod_id, singleton

# Max messages to keep in the stream to prevent memory explosion
STREAM_MAX_LEN = 1000


class MarchHareConfig:
    # List of streams for event management
    streams = {
        "PLUGIN_EVENTS": "streams:plugin_events"
    }

    # list of event types for plugin management
    events = {
        "PLUGIN_INSTALLATION": "plugin_installation",
        "PLUGIN_UNINSTALLATION": "plugin_uninstallation",
    }


@singleton
class MarchHare:
    def __init__(self):
        self.pod_id = pod_id()
        self._redis_client = get_db()
        self._stop_event = threading.Event()

        # Backoff settings
        self._base_delay = 1.0  # Start with 1 second
        self._max_delay = 60.0  # Cap at 1 minute
        self._factor = 2  # Double the wait each time
        self._retries = 0

    def stop(self):
        """Signal the consumer loop to stop."""
        self._stop_event.set()

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
                maxlen=STREAM_MAX_LEN,
                approximate=True
            )

            log.debug(f"Event {event_type} sent to stream {stream_name}")
        except Exception as e:
            log.error(f"Error publishing to Redis: {e}")

    def consume_event(self, callback: Callable, stream_name: str):
        """
        Read new messages from the stream starting from "now".
        """
        # "$" tells Redis to only return messages that arrive after we start reading
        last_id = "$"

        log.debug(f"[*] Started Redis Stream consumer on {stream_name}.")

        while not self._stop_event.is_set():
            try:
                # block=100ms so the stop flag is checked frequently
                events = self._redis_client.xread({stream_name: last_id}, count=1, block=100)

                # If we reached this point, the connection is active
                if self._retries > 0:
                    log.info("Redis connection re-established. Resetting backoff.")
                    self._retries = 0

                for stream, messages in events:
                    for message_id, data in messages:
                        # Process message
                        callback(data)
                        # Update last_id to the one we just processed to move the cursor forward
                        last_id = message_id
            except (redis.ConnectionError, redis.TimeoutError, ValueError) as e:
                if self._stop_event.is_set():
                    break  # voluntary shutdown, exit silently

                # Calculate exponential delay: (base * factor^retries) + jitter
                # Jitter prevents all pods from reconnecting at the exact same millisecond
                jitter = random.uniform(0, 1)
                delay = min(self._max_delay, (self._base_delay * (self._factor ** self._retries)) + jitter)

                log.warning(f"Redis unavailable: {e}. Retrying in {delay:.2f}s (Attempt {self._retries + 1})")

                time.sleep(delay)
                self._retries += 1
            except Exception as e:
                if self._stop_event.is_set():
                    break  # voluntary shutdown, exit silently

                log.error(f"Unexpected error in consumer loop: {e}")
                time.sleep(2)  # Brief pause for non-connection logic errors


_march_hare: Optional[MarchHare] = None
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

    _march_hare.consume_event(callback, MarchHareConfig.streams["PLUGIN_EVENTS"])


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
            thread.join(timeout=2)
    _consumer_threads = []


@hook(priority=0)
def before_lizard_bootstrap(lizard) -> None:
    global _march_hare

    _march_hare = MarchHare()
    _start_consumer_threads(lizard)


@hook(priority=0)
def after_lizard_bootstrap(lizard) -> None:
    global _march_hare

    if _march_hare is None:
        message = """For some reason, the March Hare plugin is inactive. This could be due to a Redis connection failure
during initialization. Please check the logs for more details. The plugin is fundamental to manage the PODs. The system
cannot be used without it."""
        log.error(message)
        raise Exception(message)


@hook(priority=0)
def before_lizard_shutdown(lizard) -> None:
    global _march_hare

    _march_hare.stop()
    _end_consumer_threads()
    _march_hare = None


@hook(priority=999)
def lizard_notify_plugin_installation(plugin_id: str, plugin_path: str, lizard) -> None:
    global _march_hare

    if plugin_id and lizard.plugin_manager.plugins.get(plugin_id):
        _march_hare.notify_event(
            event_type=MarchHareConfig.events["PLUGIN_INSTALLATION"],
            payload={
                "plugin_id": plugin_id,
                "plugin_path": plugin_path
            },
            stream_name=MarchHareConfig.streams["PLUGIN_EVENTS"],
        )


@hook(priority=0)
def lizard_notify_plugin_uninstallation(plugin_id, lizard) -> None:
    global _march_hare

    if lizard.plugin_manager.plugins.get(plugin_id) is None:
        _march_hare.notify_event(
            event_type=MarchHareConfig.events["PLUGIN_UNINSTALLATION"],
            payload={"plugin_id": plugin_id},
            stream_name=MarchHareConfig.streams["PLUGIN_EVENTS"],
        )
