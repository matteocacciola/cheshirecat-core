from typing import Dict, Any
from redis.exceptions import RedisError

from cat.core_plugins.analytics.constants import KEY_PREFIX
from cat.core_plugins.analytics.cruds.base import (
    get_analytics as base_get_analytics,
    get_nested_analytics,
    set_analytics as base_set_analytics,
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


def get_analytics(agent_id: str = "*", embedder_id: str = "*") -> Dict[str, Dict[str, Any]]:
    """
    Retrieve analytics data from Redis based on agent and embedder patterns.

    Args:
        agent_id: Agent ID or "*" for all agents
        embedder_id: Embedder ID or "*" for all embedders

    Returns:
        Nested dictionary: {agent_id: {embedder_id: content}}
    """
    try:
        pattern = format_key(agent_id, embedder_id)
        return get_nested_analytics(pattern, expected_parts=3)
    except RedisError as e:
        log.error(f"Redis error while fetching analytics for the Embedders: {e}")
        raise


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
        analytics = base_get_analytics(key) or {}
        analytics["files"] = analytics.get("files", {})
        analytics["files"][filename] = analytics["files"].get(filename, 0) + n_embeddings
        analytics["total_embeddings"] = analytics.get("total_embeddings", 0) + n_embeddings

        return base_set_analytics(key, analytics)
    except (RedisError, ValueError) as e:
        log.error(f"Error updating settings for {key.replace(KEY_PREFIX + ':', '')}: {e}")
        raise
