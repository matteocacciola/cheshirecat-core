from datetime import datetime, timezone
from typing import Dict
from uuid import uuid4
from redis.exceptions import RedisError

from cat.auth.auth_utils import check_password
from cat.db import crud
from cat.db.database import DEFAULT_AGENTS_KEY, DEFAULT_SYSTEM_KEY, DEFAULT_USERS_KEY
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


def format_key(agent_id: str, user_id: str) -> str:
    """
    Format Redis key for users.

    Args:
        agent_id: ID of the chatbot.
        user_id: ID of the user.

    Returns:
        Formatted key (e.g., "agents:<agent_id>:users:<user_id>" or "system:users:<user_id>" for the system agent).
    """
    return (
        f"{DEFAULT_SYSTEM_KEY}:{DEFAULT_USERS_KEY}:{user_id}"
        if agent_id == DEFAULT_SYSTEM_KEY
        else f"{DEFAULT_AGENTS_KEY}:{agent_id}:{DEFAULT_USERS_KEY}:{user_id}"
    )


def get_users(
    agent_id: str,
    with_password: bool = False,
    with_timestamps: bool = False,
    limit: int | None = None,
    offset: int = 0
) -> Dict[str, Dict]:
    """
    Retrieve users for a given agent from Redis with optional pagination.

    Args:
        agent_id: Agent ID.
        with_password: Include password field if True.
        with_timestamps: Include created_at and updated_at fields if True.
        limit: Maximum number of users to return (None = all users).
        offset: Number of users to skip (for pagination).

    Returns:
        Dictionary of users, or empty dict if none found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        # Get database connection
        db = crud.get_db()

        # Scan for user keys matching the pattern
        pattern = format_key(agent_id, "*")
        cursor = 0
        all_keys = []

        while True:
            cursor, keys = db.scan(cursor, match=pattern, count=100)
            all_keys.extend(keys)
            if cursor == 0:
                break

        if not all_keys:
            return {}

        paginated_keys = all_keys

        # If pagination is requested, we need to collect keys first to apply offset/limit
        # For non-paginated requests with large datasets, consider using get_users_paginated instead
        if limit is not None or offset > 0:
            # Apply pagination
            total_keys = len(all_keys)
            if offset >= total_keys:
                return {}

            end_index = offset + limit if limit is not None else total_keys
            paginated_keys = all_keys[offset:end_index]

        if not paginated_keys:
            return {}

        # Batch read user data using pipeline
        pipe = db.pipeline()
        for key in paginated_keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            pipe.json().get(key_str)

        users_data = pipe.execute()

        # Build result dictionary
        excluded_keys = []
        if not with_timestamps:
            excluded_keys.extend(["created_at", "updated_at"])
        if not with_password:
            excluded_keys.append("password")

        result = {}
        for key, user_data in zip(paginated_keys, users_data):
            if not user_data:
                continue
            # Extract user_id from the key (last part after the last colon)
            key_str = key.decode() if isinstance(key, bytes) else key
            user_id = key_str.split(":")[-1]

            # Filter out excluded keys
            result[user_id] = {k: v for k, v in user_data.items() if k not in excluded_keys}

        return result
    except RedisError as e:
        log.error(f"Redis error getting users for {agent_id}: {e}")
        raise


def get_users_stream(
    agent_id: str,
    with_password: bool = False,
    with_timestamps: bool = False,
    batch_size: int = 100
):
    """
    Stream users for a given agent from Redis in batches (generator function).

    This is optimal for very large datasets (100k+ users) as it doesn't load all keys
    into memory at once. Use this when you need to process all users but want to
    avoid memory issues.

    Args:
        agent_id: Agent ID.
        with_password: Include password field if True.
        with_timestamps: Include created_at and updated_at fields if True.
        batch_size: Number of users to process per batch.

    Yields:
        Tuples of (user_id, user_data) for each user.

    Raises:
        RedisError: If Redis connection fails.

    Example:
        for user_id, user_data in get_users_stream("agent_123"):
            process_user(user_id, user_data)
    """
    try:
        db = crud.get_db()
        pattern = format_key(agent_id, "*")
        cursor = 0

        # Build exclusion list
        excluded_keys = []
        if not with_timestamps:
            excluded_keys.extend(["created_at", "updated_at"])
        if not with_password:
            excluded_keys.append("password")

        while True:
            # Scan for next batch of keys
            cursor, keys = db.scan(cursor, match=pattern, count=batch_size)

            if keys:
                # Batch read this chunk of users
                pipe = db.pipeline()
                for key in keys:
                    key_str = key.decode() if isinstance(key, bytes) else key
                    pipe.json().get(key_str)

                users_data = pipe.execute()

                # Yield each user in this batch
                for key, user_data in zip(keys, users_data):
                    if user_data:
                        key_str = key.decode() if isinstance(key, bytes) else key
                        user_id = key_str.split(":")[-1]

                        # Filter out excluded keys
                        filtered_data = {k: v for k, v in user_data.items() if k not in excluded_keys}
                        yield user_id, filtered_data

            # If cursor is 0, we've scanned all keys
            if cursor == 0:
                break

    except RedisError as e:
        log.error(f"Redis error streaming users for {agent_id}: {e}")
        raise


def create_user(agent_id: str, new_user: Dict) -> Dict | None:
    """
    Create a new user in Redis atomically.

    Args:
        agent_id: Agent ID.
        new_user: Dictionary with user data (must include 'username' and 'password').

    Returns:
        Created user dictionary (without the password), or None if the user exists.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If user data is invalid or serialization fails.
    """
    try:
        if not new_user.get("username") or not new_user.get("password"):
            raise ValueError("Username and password are required")

        if get_user_by_username(agent_id, new_user["username"], with_password=True):
            log.debug(f"User {new_user['username']} already exists for {agent_id}")
            return None

        existing_id = new_user.get("id")
        if existing_id and get_user(agent_id, existing_id):
            log.debug(f"User ID {existing_id} already exists for {agent_id}")
            return None

        new_id = existing_id or str(uuid4())
        new_user_copy = new_user.copy()
        new_user_copy["id"] = new_id
        new_user_copy["created_at"] = datetime.now(timezone.utc).timestamp()
        new_user_copy["updated_at"] = new_user_copy["created_at"]

        # Store user in its own Redis key
        crud.store(format_key(agent_id, new_id), new_user_copy)
        log.debug(f"Created user {new_id} for {agent_id}")

        return _extract_user_data(new_user_copy)
    except (RedisError, ValueError) as e:
        log.error(f"Error creating user for {agent_id}: {e}")
        raise


def _get_user_by(agent_id: str, key: str, value: str, full: bool = False) -> Dict | None:
    """
    Helper function to retrieve a user by a specific key.

    Args:
        agent_id: Agent ID.
        key: The key to search by (e.g., 'id' or 'username').
        value: The value to search for.
        full: If True, include password and timestamps.

    Returns:
        User dictionary, or None if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        # Optimize: for 'id' lookup, directly read the specific key
        if key == "id":
            user_data = crud.read(format_key(agent_id, value))
            if not user_data:
                log.debug(f"No user found for {agent_id}, id: {value}")
                return None

            if isinstance(user_data, list):
                user_data = user_data[0]
            log.debug(f"Retrieved user {value} for {agent_id}")
            if full:
                return user_data
            return _extract_user_data(user_data)

        # For other lookups (e.g., username), scan and process in batches with early exit
        # This avoids loading all users into memory at once
        db = crud.get_db()
        pattern = format_key(agent_id, "*")
        cursor = 0
        batch_size = 100  # Process in batches to avoid memory issues with large datasets

        while True:
            # Scan for next batch of keys
            cursor, keys = db.scan(cursor, match=pattern, count=batch_size)

            if keys:
                # Batch read this chunk of users using pipeline
                pipe = db.pipeline()
                for user_key in keys:
                    key_str = user_key.decode() if isinstance(user_key, bytes) else user_key
                    pipe.json().get(key_str)

                users_data = pipe.execute()

                # Check this batch for a match (early exit on first match)
                for user_data in users_data:
                    if user_data and user_data.get(key) == value:
                        log.debug(f"Retrieved user {value} for {agent_id}")
                        if full:
                            return user_data
                        return _extract_user_data(user_data)

            # If cursor is 0, we've scanned all keys
            if cursor == 0:
                break

        log.debug(f"No user found for {agent_id}, {key}: {value}")
        return None
    except RedisError as e:
        log.error(f"Redis error getting user {value} for {agent_id}: {e}")
        raise


def get_user(agent_id: str, user_id: str, full: bool = False) -> Dict | None:
    return _get_user_by(agent_id, "id", user_id, full)


def get_user_by_username(agent_id: str, username: str, with_password: bool = False) -> Dict | None:
    return _get_user_by(agent_id, "username", username, with_password)


def update_user(agent_id: str, user_id: str, updated_info: Dict) -> Dict | None:
    """
    Update a user in Redis atomically.

    Args:
        agent_id: Agent ID.
        user_id: ID of the user.
        updated_info: Updated user data (must include 'username' and optionally 'password').

    Returns:
        Updated user dictionary (without password or timestamps), or None if user not found.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If user data is invalid or serialization fails.
    """
    try:
        # Get existing user with password
        if not (existing_user := get_user(agent_id, user_id, full=True)):
            log.debug(f"User {user_id} not found for {agent_id}")
            return None

        updated_info_copy = updated_info.copy()
        updated_info_copy["id"] = user_id
        updated_info_copy["created_at"] = existing_user.get("created_at")
        updated_info_copy["updated_at"] = datetime.now(timezone.utc).timestamp()
        updated_info_copy["password"] = (
            updated_info_copy["password"]
            if "password" in updated_info_copy
            else existing_user.get("password")
        )

        # Update the user's individual key
        crud.store(format_key(agent_id, user_id), updated_info_copy)
        log.debug(f"Updated user {user_id} for {agent_id}")

        return _extract_user_data(updated_info_copy)
    except (RedisError, ValueError) as e:
        log.error(f"Error updating user {user_id} for {agent_id}: {e}")
        raise


def delete_user(agent_id: str, user_id: str) -> Dict | None:
    """
    Delete a user from Redis atomically.

    Args:
        agent_id: Agent ID.
        user_id: ID of the user.

    Returns:
        Deleted user dictionary (with all fields), or None if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        # Get user before deleting to return it
        if not (user := get_user(agent_id, user_id, full=True)):
            log.debug(f"User {user_id} not found for {agent_id}")
            return None

        # Delete the entire user key
        db = crud.get_db()
        db.delete(format_key(agent_id, user_id))

        log.debug(f"Deleted user {user_id} for {agent_id}")
        return user
    except RedisError as e:
        log.error(f"Redis error deleting user {user_id} for {agent_id}: {e}")
        raise


def get_user_by_credentials(agent_id: str, username: str, password: str) -> Dict | None:
    """
    Authenticate a user by username and password.

    Args:
        agent_id: Agent ID.
        username: Username of the user.
        password: Password to verify.

    Returns:
        User dictionary (without password), or None if authentication fails.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        user = get_user_by_username(agent_id, username, with_password=True)
        if not user:
            log.debug(f"Authentication failed: user {username} not found for {agent_id}")
            return None

        if check_password(password, user["password"]):
            log.debug(f"Authenticated user {username} for {agent_id}")
            return {k: v for k, v in user.items() if k != "password"}

        log.debug(f"Authentication failed: incorrect password for {username} in {agent_id}")
        return None
    except RedisError as e:
        log.error(f"Redis error authenticating user {username} for {agent_id}: {e}")
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
        # Use the wildcard pattern to destroy all user keys for this agent
        pattern = format_key(agent_id, "*")
        crud.destroy(pattern)
        log.debug(f"Destroyed all user keys for {agent_id}")
    except RedisError as e:
        log.error(f"Redis error destroying users for {agent_id}: {e}")
        raise
