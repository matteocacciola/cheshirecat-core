from os import getenv
from typing import Dict, List, Any
from redis.exceptions import RedisError

from cat.db import crud
from cat.log import log
from cat.memory.messages import ConversationHistoryItem


def _get_expiration() -> int | None:
    expiration = getenv("CCAT_HISTORY_EXPIRATION")
    if expiration is None:
        return None

    try:
        expiration = int(expiration) * 60
        if expiration <= 0:
            raise ValueError("CCAT_HISTORY_EXPIRATION must be positive")

        return expiration
    except ValueError as e:
        log.error(f"Invalid CCAT_HISTORY_EXPIRATION: {e}")
        raise ValueError(f"Invalid CCAT_HISTORY_EXPIRATION: {e}")


def format_key(agent_id: str, user_id: str, chat_id: str) -> str:
    """
    Format Redis key for a conversation.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.

    Returns:
        Formatted key (e.g., "agent_id:history:user_id").
    """
    return f"{agent_id}:history:{user_id}:{chat_id}"


def get_histories(agent_id: str, user_id: str) -> Dict[str, List[Dict[str, Any]]]:
    """
    Retrieve conversation histories from Redis.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.

    Returns:
        Dictionary of chat_id to list of conversation history items, or empty dict if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        histories = {}
        # Construct the pattern to find all keys for the user
        pattern = format_key(agent_id, user_id, "*")

        db = crud.get_db()

        # Use scan_iter for efficient key discovery without blocking the server
        for key_str in db.scan_iter(match=pattern):
            # Extract the chat_id from the key string
            parts = key_str.split(":")
            if len(parts) != 4:
                continue
            agent_id, _, user_id, chat_id = parts

            # Retrieve the history for the specific key
            history_data = get_history(agent_id, user_id, chat_id)
            if history_data:
                histories[chat_id] = history_data

        return histories
    except RedisError as e:
        log.error(f"Failed to get histories for {agent_id}:{user_id}: {e}")
        raise

def get_history(agent_id: str, user_id: str, chat_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve conversation history from Redis.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.

    Returns:
        List of conversation history items, or empty list if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        history = crud.read(format_key(agent_id, user_id, chat_id))
        return history if history else []
    except RedisError as e:
        log.error(f"Failed to get history for {agent_id}:{user_id}: {e}")
        raise


def set_history(
    agent_id: str, user_id: str, chat_id: str, history: List[ConversationHistoryItem]
) -> List[Dict[str, Any]]:
    """
    Store conversation history in Redis with optional TTL.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.
        history: List of conversation history items.

    Returns:
        Stored history.

    Raises:
        ValueError: If CCAT_HISTORY_EXPIRATION is invalid.
        RedisError: If Redis connection fails.
    """

    try:
        formatted = [message.model_dump(exclude={"chat_id"}) for message in history]
        expiration = _get_expiration()
        crud.store(format_key(agent_id, user_id, chat_id), formatted, expire=expiration)

        return formatted
    except RedisError as e:
        log.error(f"Redis error storing history for '{agent_id}:{user_id}:{chat_id}': {e}")
        raise


def update_history(
    agent_id: str, user_id: str, chat_id: str, updated_info: ConversationHistoryItem
) -> List[Dict[str, Any]]:
    """
    Append a new item to the conversation history in Redis atomically.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.
        updated_info: New conversation item to append.

    Returns:
        Updated conversation history.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization or TTL configuration fails.
    """
    try:
        updated_info = crud.serialize_to_redis_json(updated_info.model_dump())
        history_db = get_history(agent_id, user_id, chat_id)
        history_db.append(updated_info)

        log.debug(f"Appended history item for {agent_id}:{user_id}")
        return set_history(
            agent_id,
            user_id,
            chat_id,
            [ConversationHistoryItem(**(item | {"chat_id": chat_id})) for item in history_db],
        )
    except (RedisError, ValueError) as e:
        log.error(f"Redis error updating history for {agent_id}:{user_id}: {e}")
        raise


def delete_history(agent_id: str, user_id: str, chat_id: str):
    """
    Delete conversation history for a specific user and agent.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        return crud.delete(format_key(agent_id, user_id, chat_id))
    except RedisError as e:
        log.error(f"Redis error deleting history for {agent_id}:{user_id}: {e}")
        raise


def destroy_all(agent_id: str):
    """
    Delete all conversation histories for a specific agent.

    Args:
        agent_id: ID of the chatbot.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.destroy(format_key(agent_id, "*", "*"))
    except RedisError as e:
        log.error(f"Redis error destroying histories for {agent_id}: {e}")
        raise