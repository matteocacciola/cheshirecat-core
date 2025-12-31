from datetime import datetime, timezone
from typing import Dict
from uuid import uuid4
from redis.exceptions import RedisError

from cat.auth.auth_utils import check_password
from cat.db import crud
from cat.log import log


def _extract_user_data(user_data: Dict, excluded_keys: Dict | None = None) -> Dict:
    """
    Extract user data, excluding sensitive fields.

    Args:
        user_data: Dictionary containing user data.
        excluded_keys: List of keys to exclude from the result (e.g., "created_at", "updated_at", "password").

    Returns:
        Filtered user data dictionary without excluded keys.
    """
    if excluded_keys is None:
        excluded_keys = ["password"]
    return {k: v for k, v in user_data.items() if k not in excluded_keys}


def format_key(agent_id: str) -> str:
    """
    Format Redis key for users.

    Args:
        agent_id: ID of the chatbot.

    Returns:
        Formatted key (e.g., "<agent_id>:users").
    """
    return f"{agent_id}:users"


def get_users(key_id: str, with_password: bool = False, with_timestamps: bool = False) -> Dict[str, Dict]:
    """
    Retrieve all users for a given agent from Redis.

    Args:
        key_id: Agent ID.
        with_password: Include password field if True.
        with_timestamps: Include created_at and updated_at fields if True.

    Returns:
        Dictionary of users, or empty dict if none found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        users = crud.read(format_key(key_id))
        if isinstance(users, list):
            users = users[0]

        if not users:
            return {}

        excluded_keys = []
        if not with_timestamps:
            excluded_keys.extend(["created_at", "updated_at"])
        if not with_password:
            excluded_keys.append("password")

        return {
            uid: {k: v for k, v in u.items() if k not in excluded_keys}
            for uid, u in users.items()
        }
    except RedisError as e:
        log.error(f"Redis error getting users for {key_id}: {e}")
        raise


def initialize_empty_users(key_id: str):
    """
    Store users dictionary in Redis.

    Args:
        key_id: Agent ID.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization fails.
    """
    try:
        crud.store(format_key(key_id), {})
    except (RedisError, ValueError) as e:
        log.error(f"Error storing empty user for {key_id}: {e}")
        raise


def create_user(key_id: str, new_user: Dict) -> Dict | None:
    """
    Create a new user in Redis atomically.

    Args:
        key_id: Agent ID.
        new_user: Dictionary with user data (must include 'username' and 'password').

    Returns:
        Created user dictionary (without password), or None if user exists.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If user data is invalid or serialization fails.
    """
    try:
        if not new_user.get("username") or not new_user.get("password"):
            raise ValueError("Username and password are required")

        if get_user_by_username(key_id, new_user["username"], with_password=True):
            log.debug(f"User {new_user['username']} already exists for {key_id}")
            return None

        existing_id = new_user.get("id")
        if existing_id and get_user(key_id, existing_id):
            log.debug(f"User ID {existing_id} already exists for {key_id}")
            return None

        new_id = existing_id or str(uuid4())
        new_user_copy = new_user.copy()
        new_user_copy["id"] = new_id
        new_user_copy["created_at"] = datetime.now(timezone.utc).timestamp()
        new_user_copy["updated_at"] = new_user_copy["created_at"]

        # create user
        crud.store(format_key(key_id), new_user_copy, path=f"$.{new_id}")
        log.debug(f"Created user {new_id} for {key_id}")

        return _extract_user_data(new_user_copy)
    except (RedisError, ValueError) as e:
        log.error(f"Error creating user for {key_id}: {e}")
        raise


def _get_user_by(key: str, key_id: str, identifier: str, full: bool = False) -> Dict | None:
    """
    Helper function to retrieve a user by a specific key.

    Args:
        key: The key to search by (e.g., 'id' or 'username').
        key_id: Agent ID.
        identifier: The value to search for.

    Returns:
        User dictionary, or None if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        path = f'$.[?(@.{key}=="{identifier}")]'
        result = crud.read(format_key(key_id), path)
        if not result:
            log.debug(f"No user found for {key_id}, {key}: {identifier}")
            return None

        log.debug(f"Retrieved user {identifier} for {key_id}")
        if full:
            return result[0]

        return _extract_user_data(result[0])
    except RedisError as e:
        log.error(f"Redis error getting user {identifier} for {key_id}: {e}")
        raise


def get_user(key_id: str, user_id: str, full: bool = False) -> Dict | None:
    return _get_user_by("id", key_id, user_id, full)


def get_user_by_username(key_id: str, username: str, with_password: bool = False) -> Dict | None:
    return _get_user_by("username", key_id, username, with_password)


def update_user(key_id: str, user_id: str, updated_info: Dict) -> Dict | None:
    """
    Update a user in Redis atomically.

    Args:
        key_id: Agent ID.
        user_id: ID of the user.
        updated_info: Updated user data (must include 'username' and optionally 'password').

    Returns:
        Updated user dictionary (without password or timestamps), or None if user not found.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If user data is invalid or serialization fails.
    """
    try:
        if not (existing_user := get_user(key_id, user_id)):
            log.debug(f"User {user_id} not found for {key_id}")
            return None

        updated_info_copy = updated_info.copy()
        updated_info_copy["updated_at"] = datetime.now(timezone.utc).timestamp()
        updated_info_copy["password"] = (
            updated_info_copy["password"]
            if "password" in updated_info_copy
            else existing_user.get("password")
        )

        crud.store(format_key(key_id), updated_info_copy, path=f"$.{user_id}")
        log.debug(f"Updated user {user_id} for {key_id}")

        return _extract_user_data(updated_info_copy)
    except (RedisError, ValueError) as e:
        log.error(f"Error updating user {user_id} for {key_id}: {e}")
        raise


def delete_user(key_id: str, user_id: str) -> Dict | None:
    """
    Delete a user from Redis atomically.

    Args:
        key_id: Agent ID.
        user_id: ID of the user.

    Returns:
        Deleted user dictionary (with all fields), or None if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        if not (user := get_user(key_id, user_id)):
            log.debug(f"User {user_id} not found for {key_id}")
            return None

        crud.delete(format_key(key_id), f"$.{user_id}")

        log.debug(f"Deleted user {user_id} for {key_id}")
        return user
    except RedisError as e:
        log.error(f"Redis error deleting user {user_id} for {key_id}: {e}")
        raise


def get_user_by_credentials(key_id: str, username: str, password: str) -> Dict | None:
    """
    Authenticate a user by username and password.

    Args:
        key_id: Agent ID.
        username: Username of the user.
        password: Password to verify.

    Returns:
        User dictionary (without password), or None if authentication fails.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        user = get_user_by_username(key_id, username, with_password=True)
        if not user:
            log.debug(f"Authentication failed: user {username} not found for {key_id}")
            return None

        if check_password(password, user["password"]):
            log.debug(f"Authenticated user {username} for {key_id}")
            return {k: v for k, v in user.items() if k != "password"}

        log.debug(f"Authentication failed: incorrect password for {username} in {key_id}")
        return None
    except RedisError as e:
        log.error(f"Redis error authenticating user {username} for {key_id}: {e}")
        raise


def destroy_all(agent_id: str):
    """
    Delete all users for a specific agent from Redis.

    Args:
        agent_id: ID of the chatbot.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.destroy(format_key(agent_id))
        log.debug(f"Destroyed user keys for {agent_id}")
    except RedisError as e:
        log.error(f"Redis error destroying users for {agent_id}: {e}")
        raise
