from enum import Enum
from typing import List, Dict
from redis.exceptions import RedisError

from cheshirecat.db.database import get_db as get_db_base, DEFAULT_SYSTEM_KEY
from cheshirecat.log import log


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


def read(key: str, path: str | None = "$") -> List[Dict] | Dict | None:
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
        value = get_db().json().get(key, path)
        if not value:
            return None

        if isinstance(value, list) and isinstance(value[0], list):
            return value[0]

        return value
    except RedisError as e:
        log.error(f"Redis read error for key {key}: {e}")
        raise


def store(
    key: str, value: List | Dict, path: str | None = "$", nx: bool = False, xx: bool = False, expire: int | None = None
) -> List[Dict] | Dict | None:
    """
    Store a value in Redis as JSON, with optional TTL.

    Args:
        key: Redis key to store.
        value: List or dict to store.
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
        formatted = serialize_to_redis_json(value)
        pipeline = get_db().pipeline()
        pipeline.json().set(key, path, formatted, nx=nx, xx=xx)
        if expire:
            pipeline.expire(key, expire)

        if not pipeline.execute():
            return None

        log.debug(f"Stored key {key}, TTL: {expire}")
        return value
    except (RedisError, ValueError) as e:
        log.error(f"Serialization error for key {key}: {e}")
        raise


def delete(key: str, path: str = "$"):
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
        get_db().json().delete(key, path)
        log.debug(f"Deleted path {path} for key {key}")
    except RedisError as e:
        log.error(f"Redis delete error for key {key}: {e}")
        raise


def destroy(key_pattern: str):
    """
    Delete all keys matching a pattern.

    Args:
        key_pattern: Pattern to match keys (e.g., "agent_id:*").

    Returns:
        Number of keys deleted.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        for k in get_db().scan_iter(key_pattern):
            get_db().delete(k)
        log.debug(f"Destroyed all keys matching {key_pattern}")
    except RedisError:
        raise


def get_agents_main_keys() -> List[str]:
    """
    Get all unique agent IDs from Redis keys, excluding DEFAULT_SYSTEM_KEY.

    Returns:
        List of unique agent IDs.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        return list({k.split(":")[0] for k in get_db().scan_iter("*") if k.split(":")[0] != DEFAULT_SYSTEM_KEY})
    except RedisError as e:
        log.error(f"Redis error in get_agents_main_keys: {e}")
        raise


def get_db():
    """
    Get the Redis database connection.

    Returns:
        Redis database connection.
    """
    return get_db_base()
