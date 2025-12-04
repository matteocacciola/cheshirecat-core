from enum import Enum
from typing import List, Dict
from redis.exceptions import RedisError

from cat.db.database import (
    get_db as get_db_base,
    get_db_connection_string as get_db_connection_string_base,
    DEFAULT_SYSTEM_KEY,
)
from cat.log import log


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

        return value  # type: ignore
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

        log.debug(f"Stored key {key}, value {value}, TTL: {expire}")
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
        return list({ks for k in get_db().scan_iter("*") if (ks := k.split(":")[0]) != DEFAULT_SYSTEM_KEY})
    except RedisError as e:
        log.error(f"Redis error in get_agents_main_keys: {e}")
        raise


def get_agents_plugin_keys(plugin_name: str) -> List[str]:
    """
    Get all unique agent IDs from Redis keys that have the format *:plugin_id:<plugin_name>.

    Args:
        plugin_name: The name of the plugin to filter by.

    Returns:
        List of unique agent IDs that have keys matching the plugin format.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        pattern = f"*:plugin:{plugin_name}"
        return list({ks for k in get_db().scan_iter(pattern) if (ks := k.split(":")[0]) != DEFAULT_SYSTEM_KEY})
    except RedisError as e:
        log.error(f"Redis error in get_agents_plugin_keys: {e}")
        raise


def clone_agent(source_prefix: str, target_prefix: str, skip_keys: List[str] | None = None) -> int:
    """
    Clone all keys with source_prefix to target_prefix.

    Args:
        source_prefix: Source key prefix (e.g., "agent_test")
        target_prefix: Target key prefix (e.g., "test_clone_agent_2")
        skip_keys: List of specific keys to skip during cloning (e.g., ["analytics"]). Optional.

    Returns:
        Number of keys cloned
    """
    skip_keys = skip_keys or []

    try:
        db = get_db()

        # Find all keys with the source prefix
        pattern = f"{source_prefix}:*"
        keys = list(db.scan_iter(match=pattern))
        # Filter out keys to skip
        keys = [
            kd
            for k in keys
            for skip_key in skip_keys
            if skip_key not in (kd := (k.decode() if isinstance(k, bytes) else k))
        ]

        if not keys:
            log.warning(f"No keys found with prefix '{source_prefix}'")
            return 0

        cloned_count = 0
        for source_key in keys:
            # Determine the target key by replacing the prefix
            target_key = source_key.replace(source_prefix, target_prefix, 1)

            # Read the source data
            source_data = db.json().get(source_key, "$")

            if source_data:
                # Handle JSONPath list wrapper
                if isinstance(source_data, list) and len(source_data) > 0:
                    source_data = source_data[0]

                # Write to target
                db.json().set(target_key, "$", source_data)
                cloned_count += 1
                log.info(f"Cloned '{source_key}' to '{target_key}'")

        return cloned_count
    except RedisError as e:
        log.error(f"Redis error in clone_agent: {e}")
        raise


def get_db():
    """
    Get the Redis database connection.

    Returns:
        Redis database connection.
    """
    return get_db_base()


def get_db_connection_string() -> str:
    return get_db_connection_string_base()
