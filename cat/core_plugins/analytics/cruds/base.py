from typing import Dict, Any, List, Tuple
from redis.exceptions import RedisError

from cat.core_plugins.analytics.constants import KEY_PREFIX
from cat.db import crud
from cat.log import log


def get_analytics(key: str) -> Dict[str, Any] | None:
    """
    Retrieve analytics from Redis.

    Args:
        key: Redis key for the analytics.

    Returns:
        Dictionary of analytics, or None if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        analytics = crud.read(key)
        if analytics is None:
            log.debug(f"No analytics found for {key.replace(KEY_PREFIX + ':', '')}")
            return None

        if isinstance(analytics, list):
            analytics = analytics[0]

        return analytics
    except RedisError as e:
        log.error(f"Redis error getting analytics for {key.replace(KEY_PREFIX + ':', '')}: {e}")
        raise


def set_analytics(key: str, analytics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store analytics in Redis.

    Args:
        key: Redis key for the analytics.
        analytics: Dictionary of analytics.

    Returns:
        Stored settings.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If settings serialization fails.
    """
    try:
        crud.store(key, analytics)

        log.debug(f"Stored analytics for {key.replace(KEY_PREFIX + ':', '')}")
        return analytics
    except (RedisError, ValueError) as e:
        log.error(f"Error storing analytics for {key.replace(KEY_PREFIX + ':', '')}: {e}")
        raise


def _scan_keys_with_pattern(db, pattern: str, batch_size: int = 100) -> List[bytes]:
    """
    Scan Redis for all keys matching a pattern.

    Args:
        db: Redis database connection
        pattern: Key pattern to match
        batch_size: Number of keys to fetch per SCAN iteration

    Returns:
        List of all matching keys
    """
    all_keys = []
    cursor = 0

    while True:
        cursor, keys = db.scan(cursor, match=pattern, count=batch_size)
        all_keys.extend(keys)

        if cursor == 0:
            break

    return all_keys


def _parse_key_parts(key: bytes | str, expected_parts: int) -> Tuple[str, ...] | None:
    """
    Parse a Redis key into its component parts.

    Args:
        key: Redis key (bytes or string)
        expected_parts: Expected number of parts after splitting (including prefix)

    Returns:
        Tuple of key parts, or None if invalid
    """
    key_str = key.decode() if isinstance(key, bytes) else key
    parts = key_str.split(":", expected_parts - 1)

    if len(parts) == expected_parts:
        return tuple(parts[:1] + parts[2:])  # Exclude prefix at index 1

    return None


def _batch_read_json(db, keys: List[bytes | str]) -> List[Any]:
    """
    Read multiple JSON values from Redis using pipelining.

    Args:
        db: Redis database connection
        keys: List of Redis keys to read

    Returns:
        List of JSON contents in the same order as keys
    """
    if not keys:
        return []

    pipe = db.pipeline()
    for key in keys:
        key_str = key.decode() if isinstance(key, bytes) else key
        pipe.json().get(key_str)

    return pipe.execute()


def _build_nested_result(
    key_parts_list: List[Tuple[str, ...]],
    contents: List[Any],
) -> Dict:
    """
    Build a nested dictionary from key parts and contents.

    Args:
        key_parts_list: List of tuples containing key components (e.g., (agent, embedder))
        contents: List of content values corresponding to each key

    Returns:
        Nested dictionary structure
    """
    result = {}

    for parts, content in zip(key_parts_list, contents):
        if not content:
            continue

        # Navigate/create nested structure
        current = result
        for part in parts[:-1]:
            current = current.setdefault(part, {})

        # Set the final value
        current[parts[-1]] = content

    return result


def get_nested_analytics(pattern: str, expected_parts: int) -> Dict:
    db = crud.get_db()

    # Scan for all matching keys
    keys = _scan_keys_with_pattern(db, pattern)

    if not keys:
        return {}

    # Parse keys and prepare for batch read
    key_parts_list = []
    valid_keys = []

    for key in keys:
        parts = _parse_key_parts(key, expected_parts=expected_parts)
        if parts:
            key_parts_list.append(parts)
            valid_keys.append(key)

    # Batch read all JSON contents
    contents = _batch_read_json(db, valid_keys)

    # Build nested result
    return _build_nested_result(key_parts_list, contents)
