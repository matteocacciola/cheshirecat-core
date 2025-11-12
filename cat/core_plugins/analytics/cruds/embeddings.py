from typing import Dict, Any
from redis.exceptions import RedisError

from cat.core_plugins.analytics.constants import KEY_PREFIX
from cat.core_plugins.analytics.cruds.base import (
    get_analytics as base_get_analytics,
    set_analytics as base_set_analytics
)
from cat.log import log


def format_key(agent_id: str, embedder_id: str) -> str:
    """
    Format Redis key for an Embedding analytic.

    Args:
        agent_id: ID of the chatbot.
        embedder_id: ID of the Embedder.

    Returns:
        Formatted key.
    """
    return f"{KEY_PREFIX}:{agent_id}:{embedder_id}"


def get_analytics(agent_id: str, embedder_id: str) -> Dict[str, Any] | None:
    key = format_key(agent_id, embedder_id)
    return base_get_analytics(key)


def set_analytics(agent_id: str, embedder_id: str, analytics: Dict[str, Any]) -> Dict[str, Any]:
    key = format_key(agent_id, embedder_id)
    return base_set_analytics(key, analytics)


def update_analytics(agent_id: str, embedder_id: str, filename: str, n_embeddings: int) -> Dict[str, Any]:
    """
    Update Embedder analytics in Redis atomically.

    Args:
        agent_id: ID of the chatbot.
        embedder_id: ID of the Embedder.
        filename: Name of the file processed.
        n_embeddings: Number of embeddings created.

    Returns:
        Updated Embedder analytics.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization fails.
    """
    key = format_key(agent_id, embedder_id)

    try:
        analytics = get_analytics(agent_id, embedder_id) or {}
        analytics["files"] = analytics.get("files", {})
        analytics["files"][filename] = analytics["files"].get(filename, 0) + n_embeddings
        analytics["total_embeddings"] = analytics.get("total_embeddings", 0) + n_embeddings

        return set_analytics(agent_id, embedder_id, analytics)
    except (RedisError, ValueError) as e:
        log.error(f"Error updating settings for {key.replace(KEY_PREFIX + ':', '')}: {e}")
        raise
