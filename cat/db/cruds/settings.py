from typing import Dict, List, Any
from redis.exceptions import RedisError

from cat.db import crud, models
from cat.db.database import DEFAULT_AGENTS_KEY, DEFAULT_SYSTEM_KEY, DEFAULT_AGENT_KEY
from cat.log import log


def format_key(key_id: str) -> str:
    """
    Format Redis key for settings.

    Args:
        key_id: Settings key identifier.

    Returns:
        Formatted key (e.g., "agents:<key_id>:agent" or "system:agent" for the system agent).
    """
    return (
        f"{DEFAULT_SYSTEM_KEY}:{DEFAULT_AGENT_KEY}"
        if key_id == DEFAULT_SYSTEM_KEY
        else f"{DEFAULT_AGENTS_KEY}:{key_id}:{DEFAULT_AGENT_KEY}"
    )


def get_settings(key_id: str, search: str = "") -> List[Dict]:
    """
    Retrieve settings from Redis, optionally filtered by name.

    Args:
        key_id: Settings key identifier.
        search: Optional regex pattern to filter settings by name.

    Returns:
        List of settings dictionaries, or empty list if none found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        path = f'$[?(@.name =~ ".*{search}.*")]' if search else "$"

        settings: List[Dict] = crud.read(format_key(key_id), path)
        if not settings:
            log.debug(f"No settings found for {key_id}, search: {search}")
            return []

        # Workaround: do not expose users in the settings list
        settings = [s for s in settings if s.get("name") != "users"]
        log.debug(f"Retrieved {len(settings)} settings for {key_id}, search: {search}")
        return settings
    except RedisError as e:
        log.error(f"Redis error getting settings for {key_id}: {e}")
        raise


def get_settings_by_category(key_id: str, category: str) -> Dict | None:
    """
    Retrieve settings from Redis filtered by category.

    Args:
        key_id: Settings key identifier.
        category: Category to filter settings.

    Returns:
        List of settings dictionaries, or None if none found.

    Raises:
        RedisError: If Redis connection fails.
    """
    if not category:
        log.warning(f"Empty category for {key_id}, returning empty list")
        return None

    try:
        settings: List[Dict] = crud.read(format_key(key_id), path=f'$[?(@.category=="{category}")]')
        if not settings:
            log.debug(f"No settings found for {key_id}, category: {category}")
            return None

        log.debug(f"Retrieved settings for {key_id}, category: {category}")
        return settings[0]
    except RedisError as e:
        log.error(f"Redis error getting settings by category for {key_id}: {e}")
        raise


def create_setting(key_id: str, payload: models.Setting) -> Dict:
    """
    Append a new setting to the settings list in Redis atomically.

    Args:
        key_id: Settings key identifier.
        payload: Setting object to append.

    Returns:
        Created setting dictionary.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization fails.
    """
    try:
        fkey_id = format_key(key_id)
        value = payload.model_dump()

        existing_settings = crud.read(fkey_id) or []
        existing_settings.append(value)

        crud.store(fkey_id, existing_settings)
        log.debug(f"Created setting for {key_id}: {value.get('name')}")

        return value
    except (RedisError, ValueError) as e:
        log.error(f"Error creating setting for {key_id}: {e}")
        raise


def _get_setting_by(key_id: str, what: str, value: str):
    try:
        settings: List[Dict] = crud.read(format_key(key_id), path=f'$[?(@.{what}=="{value}")]')
        if not settings:
            log.debug(f"No setting found for {key_id}, {what}: {value}")
            return None

        log.debug(f"Retrieved setting for {key_id}, {what}: {value}")
        return settings[0]
    except RedisError as e:
        log.error(f"Redis error getting setting by {what} for {key_id}: {e}")
        raise


def get_setting_by_name(key_id: str, name: str) -> Dict | None:
    """
    Retrieve a single setting by name from Redis.

    Args:
        key_id: Settings key identifier.
        name: Name of the setting.

    Returns:
        Setting dictionary, or None if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    return _get_setting_by(key_id, "name", name)


def get_setting_by_id(key_id: str, setting_id: str) -> Dict | None:
    """
    Retrieve a single setting by ID from Redis.

    Args:
        key_id: Settings key identifier.
        setting_id: ID of the setting.

    Returns:
        Setting dictionary, or None if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    return _get_setting_by(key_id, "setting_id", setting_id)


def delete_setting_by_id(key_id: str, setting_id: str):
    """
    Delete a setting by ID from Redis.

    Args:
        key_id: Settings key identifier.
        setting_id: ID of the setting to delete.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.delete(format_key(key_id), path=f'$[?(@.setting_id=="{setting_id}")]')
        log.debug(f"Deleted setting for {key_id}, setting_id: {setting_id}")
    except RedisError as e:
        log.error(f"Redis error deleting setting for {key_id}, setting_id: {setting_id}: {e}")
        raise


def delete_settings_by_category(key_id: str, category: str):
    """
    Delete all settings in a category from Redis.

    Args:
        key_id: Settings key identifier.
        category: Category of settings to delete.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.delete(format_key(key_id), path=f'$[?(@.category=="{category}")]')
        log.debug(f"Deleted settings for {key_id}, category: {category}")
    except RedisError as e:
        log.error(f"Redis error deleting settings by category for {key_id}: {e}")
        raise


def upsert_setting_by_id(key_id: str, payload: models.Setting) -> Dict | None:
    """
    Upsert a setting by ID in Redis atomically, or create it if not exists.

    Args:
        key_id: Settings key identifier.
        payload: Setting object to update or create.

    Returns:
        Updated or created setting dictionary, or None if operation fails.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization fails.
    """
    try:
        setting = get_setting_by_id(key_id, payload.setting_id)
        if not setting:
            log.debug(f"Setting {payload.setting_id} not found for {key_id}, creating")
            return create_setting(key_id, payload)

        value = payload.model_dump()
        crud.store(format_key(key_id), value, path=f'$[?(@.setting_id=="{payload.setting_id}")]')
        log.debug(f"Updated setting {payload.setting_id} for {key_id}")

        return value
    except (RedisError, ValueError) as e:
        log.error(f"Error updating setting for {key_id}, setting_id: {payload.setting_id}: {e}")
        raise


def upsert_setting_by_name(key_id: str, payload: models.Setting) -> Dict:
    """
    Upsert a setting by name in Redis atomically.

    Args:
        key_id: Settings key identifier.
        payload: Setting object to upsert.

    Returns:
        Upserted setting dictionary.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization fails.
    """
    try:
        if not get_setting_by_name(key_id, payload.name):
            log.debug(f"Setting not found by name '{payload.name}' for {key_id}, creating")
            return create_setting(key_id, payload)

        value = payload.model_dump()
        crud.store(format_key(key_id), value, path=f'$[?(@.name=="{payload.name}")]')
        log.debug(f"Upserted setting by name '{payload.name}' for {key_id}")

        return value
    except (RedisError, ValueError) as e:
        log.error(f"Error upserting setting by name for {key_id}: {e}")
        raise


def upsert_setting_by_category(key_id: str, payload: models.Setting) -> Dict:
    """
    Upsert a setting by category in Redis atomically.

    Args:
        key_id: Settings key identifier.
        payload: Setting object to upsert.

    Returns:
        Upserted setting dictionary.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization fails.
    """
    try:
        if not get_settings_by_category(key_id, payload.category):
            log.debug(f"Setting not found by category '{payload.category}' for {key_id}, creating")
            return create_setting(key_id, payload)

        value = payload.model_dump()
        crud.store(format_key(key_id), value, path=f'$[?(@.category=="{payload.category}")]')
        log.debug(f"Upserted setting by category '{payload.category}' for {key_id}")

        return value
    except (RedisError, ValueError) as e:
        log.error(f"Error upserting setting by category for {key_id}: {e}")
        raise


def destroy_all(key_id: str):
    """
    Delete all settings for a specific key from Redis.

    Args:
        key_id: Settings key identifier.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.destroy(format_key(key_id))
        log.debug(f"Destroyed settings for {key_id}")
    except RedisError as e:
        log.error(f"Redis error destroying settings for {key_id}: {e}")
        raise


def get_agents_main_keys(pattern: str | None = None) -> List[str]:
    """
    Get all unique agent IDs from Redis keys.

    Args:
        pattern: Pattern to match keys (default: None, all agent keys).

    Returns:
        List of unique agent IDs.

    Raises:
        RedisError: If Redis connection fails.
    """
    pattern = f"{DEFAULT_AGENTS_KEY}:*" if pattern is None else pattern

    try:
        return sorted(
            list({k.split(":")[1] for k in crud.get_db().scan_iter(pattern)})
        )
    except RedisError as e:
        log.error(f"Redis error in get_agents_main_keys: {e}")
        raise


def get_agents() -> List[Dict[str, Any]]:
    """
    Get all agents with their metadata.

    Returns:
        List of agents with their metadata.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        agents = []
        for agent_id in get_agents_main_keys():
            metadata = get_setting_by_name(agent_id, "metadata")
            agents.append({"agent_id": agent_id, "metadata": metadata["value"] if metadata else {}})
        return agents
    except RedisError as e:
        log.error(f"Redis error in get_agents: {e}")
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
        db = crud.get_db()

        # Find all keys with the source prefix
        pattern = f"{DEFAULT_AGENTS_KEY}:{source_prefix}:*"
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
