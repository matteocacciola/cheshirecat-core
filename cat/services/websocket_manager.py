import asyncio
import json
from typing import Dict, List
import redis.asyncio as aioredis
from fastapi.websockets import WebSocket

from cat.log import log

# Redis channel names
_TARGETED_PREFIX = "ws:msg"   # targeted: ws:msg:{chat_id}
_BROADCAST_CHANNEL = "ws:broadcast"


class WebSocketManager:
    """
    Manages WebSocket connections with Redis Pub/Sub fan-out.

    Every message is published to Redis so the replica that actually holds
    the connection receives and delivers it – regardless of which replica
    produced it.  Redis is a platform pre-requisite and is always available.

    Call ``await start()`` once during application startup.
    """

    def __init__(self):
        # chat_id → WebSocket for connections held by THIS replica
        self._local_connections: Dict[str, WebSocket] = {}

        # async Redis client (initialised by start())
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None
        self._subscriber_task: asyncio.Task | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self):
        """Connect to Redis and launch the pub/sub listener background task."""
        from cat.db.database import get_db_connection_string

        self._redis = aioredis.Redis.from_url(
            get_db_connection_string(), decode_responses=True
        )

        self._pubsub = self._redis.pubsub()  # type: ignore[no-untyped-call]
        # Pattern-subscribe for targeted messages and subscribe for broadcasts
        await self._pubsub.psubscribe(f"{_TARGETED_PREFIX}:*")  # type: ignore[no-untyped-call]
        await self._pubsub.subscribe(_BROADCAST_CHANNEL)  # type: ignore[no-untyped-call]

        self._subscriber_task = asyncio.create_task(
            self._subscriber_loop(), name="ws-pubsub-listener"
        )
        log.info("WebSocket Redis Pub/Sub listener started")

    async def _subscriber_loop(self):
        """
        Background task: listen on Redis pub/sub and deliver messages to
        WebSocket connections held by this replica.
        """
        try:
            async for raw in self._pubsub.listen():  # type: ignore[no-untyped-call]
                msg_type = raw.get("type")
                if msg_type not in ("pmessage", "message"):
                    continue

                data = raw.get("data")
                if not isinstance(data, str):
                    continue

                try:
                    payload = json.loads(data)
                except (json.JSONDecodeError, TypeError):
                    log.warning(f"WS pubsub: malformed message on channel {raw.get('channel')}")
                    continue

                if msg_type == "pmessage":
                    # Targeted message: channel is "ws:msg:<chat_id>"
                    channel: str = raw["channel"]
                    chat_id = channel[len(_TARGETED_PREFIX) + 1:]
                    await self._deliver_to_local(chat_id, payload)
                else:
                    # Broadcast to all connections on this replica
                    await self._deliver_to_all_local(payload)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            log.error(f"WebSocket Pub/Sub listener crashed: {e}")

    async def _deliver_to_local(self, chat_id: str, message: dict):
        """Send *message* to the local WebSocket for *chat_id*, if present."""
        ws = self._local_connections.get(chat_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception as e:
                log.warning(f"WS delivery failed for chat {chat_id}: {e}")

    async def _deliver_to_all_local(self, message: dict):
        """Send *message* to every WebSocket connection on this replica."""
        for chat_id, ws in list(self._local_connections.items()):
            try:
                await ws.send_json(message)
            except Exception as e:
                log.warning(f"WS broadcast delivery failed for chat {chat_id}: {e}")

    # ── Connection management ──────────────────────────────────────────────────

    def add_connection(self, chat_id: str, websocket: WebSocket):
        """Register a new WebSocket connection for *chat_id* on this replica."""
        self._local_connections[chat_id] = websocket

    def get_connection(self, chat_id: str) -> WebSocket | None:
        """Return the local WebSocket for *chat_id*, or ``None``."""
        return self._local_connections.get(chat_id)

    def remove_connection(self, chat_id: str):
        """Unregister the WebSocket connection for *chat_id*."""
        self._local_connections.pop(chat_id, None)

    # ── Sending ────────────────────────────────────────────────────────────────

    async def send_to(self, chat_id: str, message: dict):
        """
        Send *message* to the WebSocket identified by *chat_id*.

        The message is published to the Redis ``ws:msg:<chat_id>`` channel;
        the replica that holds that connection will receive the pub/sub event
        and deliver it locally.
        """
        await self._redis.publish(  # type: ignore[union-attr]
            f"{_TARGETED_PREFIX}:{chat_id}", json.dumps(message)
        )

    async def broadcast(self, message: dict):
        """Broadcast *message* to every connected WebSocket across all replicas."""
        await self._redis.publish(_BROADCAST_CHANNEL, json.dumps(message))  # type: ignore[union-attr]

    # ── Introspection ──────────────────────────────────────────────────────────

    def is_connected(self, chat_id: str) -> bool:
        """``True`` if *this replica* holds an active connection for *chat_id*."""
        return chat_id in self._local_connections

    def is_empty(self) -> bool:
        return not self._local_connections

    def is_connected_to(self, chat_id: str) -> bool:
        return self.is_connected(chat_id)

    def is_connected_to_any(self, ids: List[str]) -> bool:
        return any(self.is_connected(i) for i in ids)

    def is_connected_to_all(self, ids: List[str]) -> bool:
        return all(self.is_connected(i) for i in ids)

    def get_connections(self) -> Dict:
        return self._local_connections

    def get_connection_ids(self) -> List[str]:
        return list(self._local_connections.keys())

    def get_connection_count(self) -> int:
        return len(self._local_connections)

    # Backward-compatibility alias used by tests
    @property
    def connections(self) -> Dict:
        return self._local_connections

    # ── Shutdown ───────────────────────────────────────────────────────────────

    async def close_connections(self):
        """Close all local WebSocket connections and stop the pub/sub listener."""
        # Stop the background subscriber first
        if self._subscriber_task:
            self._subscriber_task.cancel()
            try:
                await self._subscriber_task
            except asyncio.CancelledError:
                pass
            self._subscriber_task = None

        # Close every local WebSocket
        for ws in list(self._local_connections.values()):
            try:
                await ws.close()
            except Exception:
                pass
        self._local_connections.clear()

        # Tear down pub/sub and Redis client
        if self._pubsub:
            try:
                await self._pubsub.punsubscribe()
                await self._pubsub.unsubscribe()
                await self._pubsub.aclose()
            except Exception:
                pass
            self._pubsub = None

        if self._redis:
            try:
                await self._redis.aclose()
            except Exception:
                pass
            self._redis = None

    async def close_connection(self, chat_id: str):
        """Close the WebSocket connection for *chat_id* and unregister it."""
        ws = self._local_connections.pop(chat_id, None)
        if ws:
            try:
                await ws.close()
            except Exception:
                pass

    async def close_connections_by_ids(self, ids: List[str]):
        """Close multiple WebSocket connections by their *chat_id*."""
        for chat_id in ids:
            await self.close_connection(chat_id)
