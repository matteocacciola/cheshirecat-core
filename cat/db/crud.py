from contextlib import asynccontextmanager
from enum import Enum
from typing import List, Dict, Any
from redis.exceptions import LockError, RedisError
from redis.lock import Lock
import redis.asyncio as aioredis

from cat.db.database import get_db as get_db_base, get_db_connection_string as get_db_connection_string_base
from cat.log import log


@asynccontextmanager
async def distributed_lock(key_pattern: str, timeout: float = 10.0, blocking_timeout: float = 15.0):
    """
    Acquire a distributed lock on a pattern-based operation.

    Args:
        key_pattern: The pattern being operated on (used to derive the lock key).
        timeout: How long the lock is held before auto-release (seconds).
                 Should be longer than the expected operation duration.
        blocking_timeout: How long to wait to acquire the lock before raising.

    Raises:
        LockError: If the lock cannot be acquired within blocking_timeout.
        RedisError: If Redis connection fails.
    """
    # Derive a stable lock key from the pattern, avoiding wildcard chars
    lock_key = "lock:" + key_pattern.replace("*", "_").replace(":", "_")
    lock: Lock = get_db().lock(
        lock_key,
        timeout=timeout,
        blocking_timeout=blocking_timeout,
        thread_local=False,  # Safe for async/multi-process contexts
    )

    acquired = False
    try:
        acquired = await lock.acquire()
        if not acquired:
            raise LockError(f"Could not acquire lock for pattern '{key_pattern}'")
        yield lock
    finally:
        if acquired:
            try:
                await lock.release()
            except LockError:
                # Lock expired before we released it (timeout too short)
                log.warning(f"Lock for '{key_pattern}' expired before explicit release")


def serialize_to_redis_json(data_dict: List | Dict) -> List | Dict:
    """
    Save a dictionary or list in a Redis JSON, correctly handling enums.

    Args:
        data_dict: Dictionary or list to serialize.

    Returns:
        Serialized dictionary or list for Redis JSON.

    Raises:
        ValueError: If serialization fails due to invalid data.
    """
    try:
        if isinstance(data_dict, list):
            return [serialize_to_redis_json(d) for d in data_dict]

        return {k: v.value if isinstance(v, Enum) else v for k, v in data_dict.items()}
    except Exception as e:
        log.error(f"Serialization error: {e}")
        raise ValueError(f"Failed to serialize data: {e}")


async def read(key: str, path: str | None = "$") -> List | Dict | None:
    """
    Read a JSON value from Redis.

    Args:
        key: Redis key to read.
        path: JSON path (default: "$").

    Returns:
        List or dict if found, None otherwise.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        value = await get_db().json().get(key, path)
        if not value:
            return None

        if isinstance(value, list) and isinstance(value[0], list):
            return value[0]

        return value  # type: ignore
    except RedisError as e:
        log.error(f"Redis read error for key {key}: {e}")
        raise


async def store(
    key: str, value: Any, path: str | None = "$", nx: bool = False, xx: bool = False, expire: int | None = None
) -> List[Dict] | Dict | None:
    """
    Store a value in Redis as JSON, with optional TTL.

    Args:
        key: Redis key to store.
        value: Value to store.
        path: JSON path (default: "$").
        nx: Set only if key does not exist.
        xx: Set only if key exists.
        expire: TTL in seconds (optional).

    Returns:
        Stored value if successful, None if not stored.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If TTL is invalid.
    """
    if expire and expire <= 0:
        log.warning(f"Invalid TTL {expire} for key {key}, ignoring")
        expire = None

    try:
        formatted = serialize_to_redis_json(value) if isinstance(value, (dict, list)) else value
        pipeline = get_db().pipeline()
        pipeline.json().set(key, path, formatted, nx=nx, xx=xx)  # type: ignore[arg-type]
        if expire:
            await pipeline.expire(key, expire)

        if not await pipeline.execute():
            return None

        log.debug(f"Stored key {key}, value {value}, TTL: {expire}")
        return value
    except (RedisError, ValueError) as e:
        log.error(f"Serialization error for key {key}: {e}")
        raise


async def delete(key: str, path: str | None = "$"):
    """
    Delete a JSON value or path from Redis.

    Args:
        key: Redis key to delete.
        path: JSON path (default: "$").

    Returns:
        True if deleted, False otherwise.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        await get_db().json().delete(key, path)
        log.debug(f"Deleted path {path} for key {key}")
    except RedisError as e:
        log.error(f"Redis delete error for key {key}: {e}")
        raise


async def destroy(key_pattern: str) -> int:
    """
    Delete all keys matching a pattern, serialized via a distributed lock.

    Concurrent destroy calls on the same pattern are queued rather than interleaved, so no replica can insert new
    matching keys between another replica's SCAN and DEL steps unnoticed.

    Note: this does NOT guarantee that zero keys survive if other writers keep inserting after the lock is released.

    Args:
        key_pattern: Pattern to match keys (e.g., "agents:<agent_id>:*").

    Returns:
        Number of keys deleted.

    Raises:
        LockError: If the lock cannot be acquired.
        RedisError: If Redis connection fails.
    """
    try:
        async with distributed_lock(key_pattern):
            db = get_db()
            keys = [k async for k in db.scan_iter(key_pattern)]
            if keys:
                await db.delete(*keys)
            log.debug(f"Destroyed {len(keys)} keys matching {key_pattern}")
            return len(keys)
    except (RedisError, LockError) as e:
        log.error(f"Error destroying keys for pattern '{key_pattern}': {e}")
        raise


def get_db() -> aioredis.Redis:
    """
    Return the shared async Redis client (redis.asyncio).

    Returns:
        async Redis database connection.
    """
    return get_db_base()


def get_db_connection_string() -> str:
    return get_db_connection_string_base()
