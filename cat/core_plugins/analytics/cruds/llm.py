from typing import Dict, Any
from pydantic import BaseModel
from redis.exceptions import RedisError

from cat.core_plugins.analytics.constants import KEY_PREFIX
from cat.core_plugins.analytics.cruds.base import (
    get_analytics as base_get_analytics,
    set_analytics as base_set_analytics
)
from cat.log import log


class LLMUsedTokens(BaseModel):
    input: int
    output: int


def format_key(agent_id: str, user_id: str, chat_id: str, llm_id: str) -> str:
    """
    Format Redis key for an LLM analytic.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat.
        llm_id: ID of the LLM.

    Returns:
        Formatted key.
    """
    return f"{KEY_PREFIX}:{agent_id}:{user_id}:{chat_id}:{llm_id}"


def get_analytics(agent_id: str, user_id: str, chat_id: str, llm_id: str) -> Dict[str, Any] | None:
    key = format_key(agent_id, user_id, chat_id, llm_id)
    return base_get_analytics(key)


def set_analytics(agent_id: str, user_id: str, chat_id: str, llm_id: str, analytics: Dict[str, Any]) -> Dict[str, Any]:
    key = format_key(agent_id, user_id, chat_id, llm_id)
    return base_set_analytics(key, analytics)


def update_analytics(agent_id: str, user_id: str, chat_id: str, llm_id: str, tokens: LLMUsedTokens) -> Dict[str, Any]:
    """
    Update LLM analytics in Redis atomically.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat.
        llm_id: ID of the LLM.
        tokens: LLMUsedTokens object containing input and output token counts.

    Returns:
        Updated LLM analytics.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization fails.
    """
    try:
        analytics = get_analytics(agent_id, user_id, chat_id, llm_id) or {}
        analytics["input_tokens"] = analytics.get("input_tokens", 0) + tokens.input
        analytics["output_tokens"] = analytics.get("output_tokens", 0) + tokens.output
        analytics["total_tokens"] = analytics.get("total_tokens", 0) + tokens.input + tokens.output
        analytics["total_calls"] = analytics.get("total_calls", 0) + 1

        return set_analytics(agent_id, user_id, chat_id, llm_id, analytics)
    except (RedisError, ValueError) as e:
        log.error(f"Error updating settings for key.replace(KEY_PREFIX + ':', ''): {e}")
        raise
