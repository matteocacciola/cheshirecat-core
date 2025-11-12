from typing import Dict, Any
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
