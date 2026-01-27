from os import getenv
from typing import Dict, List, Any
from redis.exceptions import RedisError

from cat.db import crud
from cat.db.database import DEFAULT_AGENTS_KEY, DEFAULT_CONVERSATIONS_KEY
from cat.log import log
from cat.services.memory.messages import ConversationMessage


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
        Formatted key (e.g., "agents:<agent_id>:conversations:<user_id>:<chat_id>").
    """
    return f"{DEFAULT_AGENTS_KEY}:{agent_id}:{DEFAULT_CONVERSATIONS_KEY}:{user_id}:{chat_id}"


def get_conversation(agent_id: str, user_id: str, chat_id: str) -> Dict[str, Any] | None:
    """
    Retrieve a specific conversation from Redis.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.

    Returns:
        Conversation data as a dictionary, or None if not found.
    """
    try:
        conversation = crud.read(format_key(agent_id, user_id, chat_id))
        if not conversation:
            return None

        if isinstance(conversation, list):
            conversation = conversation[0]

        return conversation
    except RedisError as e:
        log.error(f"Failed to get conversation '{chat_id}' for '{agent_id}:{user_id}': {e}")
        raise


def get_conversations_attributes(agent_id: str, user_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve conversations parameters from Redis. It returns the list of the chat IDs, their names and the messages
    count.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.

    Returns:
        List of dictionaries, each one having the format
            {
                "chat_id": str,
                "name": str,
                "num_messages": int,
                "metadata": dict,
                "created_at": datetime,
                "updated_at": datetime,
            }

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        results = []
        # Construct the pattern to find all keys for the user
        pattern = format_key(agent_id, user_id, "*")

        db = crud.get_db()

        # Use scan_iter for efficient key discovery without blocking the server
        for key_str in db.scan_iter(match=pattern):
            # Extract the chat_id from the key string
            parts = key_str.split(":")
            if len(parts) != 5:
                continue
            _, agent_id, _, user_id, chat_id = parts

            conversation = get_conversation_attributes(agent_id, user_id, chat_id)
            if not conversation:
                continue

            results.append(conversation)

        return results
    except RedisError as e:
        log.error(f"Failed to get chat attributes for '{agent_id}:{user_id}': {e}")
        raise


def get_conversation_attributes(agent_id: str, user_id: str, chat_id: str) -> Dict[str, Any] | None:
    """
    Retrieve conversation parameters from Redis.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.

    Returns:
        Dictionary having the format
            {
                "chat_id": str,
                "name": str,
                "num_messages": int,
                "metadata": dict,
                "created_at": datetime,
                "updated_at": datetime,
            }
        or None if conversation not found.
    """
    try:
        conversation = get_conversation(agent_id, user_id, chat_id)
        if not conversation:
            return None

        messages = conversation.get("messages", [])
        num_messages = len(messages)

        # Extract created_at (first message) and updated_at (last message)
        created_at = messages[0]["when"] if num_messages > 0 else None
        updated_at = messages[-1]["when"] if num_messages > 0 else None

        # Retrieve the conversation name for the specific key
        return {
            "chat_id": chat_id,
            "name": conversation.get("name", chat_id),
            "num_messages": num_messages,
            "metadata": conversation.get("metadata", {}),
            "created_at": created_at,
            "updated_at": updated_at,
        }
    except RedisError as e:
        log.error(f"Failed to get chat attributes for '{agent_id}:{user_id}': {e}")
        raise


def get_messages(agent_id: str, user_id: str, chat_id: str) -> List[Dict[str, Any]]:
    """
    Retrieve conversation messages from Redis.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.

    Returns:
        List of conversation messages, or empty list if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        messages = crud.read(format_key(agent_id, user_id, chat_id), path="$.messages")
        return messages if messages else []
    except RedisError as e:
        log.error(f"Failed to get conversation '{chat_id}' for '{agent_id}:{user_id}': {e}")
        raise


def set_messages(
    agent_id: str, user_id: str, chat_id: str, messages: List[ConversationMessage]
) -> List[Dict[str, Any]]:
    """
    Store conversation messages in Redis with optional TTL.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.
        messages: List of conversation messages.

    Returns:
        Stored messages.

    Raises:
        ValueError: If CCAT_HISTORY_EXPIRATION is invalid.
        RedisError: If Redis connection fails.
    """

    try:
        formatted = [message.model_dump() for message in messages]
        expiration = _get_expiration()
        key = format_key(agent_id, user_id, chat_id)

        # Check if the key exists
        existing_data = crud.read(key)

        if existing_data is None:
            # Key doesn't exist - create the entire structure at root
            crud.store(key, {"name": chat_id, "messages": formatted}, expire=expiration)
            return formatted

        # Key exists - update only the messages path
        crud.store(key, formatted, path="$.messages", expire=expiration)
        return formatted
    except RedisError as e:
        log.error(f"Redis error storing conversation '{chat_id}' for '{agent_id}:{user_id}': {e}")
        raise


def set_attributes(
    agent_id: str,
    user_id: str,
    chat_id: str,
    name: str | None = None,
    metadata: Dict[str, Any] | None = None,
    first_time: bool = False,
):
    """
    Set the name of a conversation in Redis.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.
        name: New name for the conversation, if any.
        metadata: New metadata for the conversation, if any.
        first_time: Whether this is the first time the conversation is being created.

    Raises:
        RedisError: If Redis connection fails.
    """
    if not name and not metadata:
        return

    try:
        conversation = get_conversation(agent_id, user_id, chat_id)
        if not conversation:
            return

        if name:
            crud.store(format_key(agent_id, user_id, chat_id), name, path="$.name")

        current_metadata = conversation.get("metadata", {})
        if metadata or first_time:
            current_metadata.update(metadata)
            crud.store(format_key(agent_id, user_id, chat_id), current_metadata or {}, path="$.metadata")
    except RedisError as e:
        log.error(f"Redis error setting conversation name for '{agent_id}:{user_id}:{chat_id}': {e}")
        raise


def update_messages(
    agent_id: str, user_id: str, chat_id: str, updated_info: ConversationMessage
) -> List[Dict[str, Any]]:
    """
    Append a new item to the conversation in Redis atomically.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.
        chat_id: ID of the chat session.
        updated_info: New conversation item to append.

    Returns:
        Updated conversation messages.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization or TTL configuration fails.
    """
    try:
        updated_info = crud.serialize_to_redis_json(updated_info.model_dump())
        history_db = get_messages(agent_id, user_id, chat_id)
        history_db.append(updated_info)

        log.debug(f"Appended conversation item for {agent_id}:{user_id}")
        return set_messages(
            agent_id,
            user_id,
            chat_id,
            [ConversationMessage(**item) for item in history_db],
        )
    except (RedisError, ValueError) as e:
        log.error(f"Redis error updating conversation '{chat_id}' for '{agent_id}:{user_id}': {e}")
        raise


def delete_conversation(agent_id: str, user_id: str, chat_id: str):
    """
    Delete conversation for a specific user and agent.

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
        log.error(f"Redis error deleting conversation '{chat_id}' for '{agent_id}:{user_id}': {e}")
        raise


def delete_conversations(agent_id: str, user_id: str):
    """
    Delete conversation for a specific user and agent.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        return crud.delete(format_key(agent_id, user_id, "*"))
    except RedisError as e:
        log.error(f"Redis error deleting conversations for {agent_id}:{user_id}: {e}")
        raise


def destroy_all(agent_id: str):
    """
    Delete all conversations for a specific agent.

    Args:
        agent_id: ID of the chatbot.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.destroy(format_key(agent_id, "*", "*"))
    except RedisError as e:
        log.error(f"Redis error destroying conversations for {agent_id}: {e}")
        raise


def get_user_id_from_conversation_keys(agent_id: str, chat_id: str) -> str | None:
    pattern = format_key(agent_id, "*", chat_id)

    user_ids = list({k.split(":")[3] for k in crud.get_db().scan_iter(pattern)})
    return user_ids[0] if len(user_ids) == 1 else None
