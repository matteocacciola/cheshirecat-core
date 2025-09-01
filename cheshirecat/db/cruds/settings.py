from typing import Dict, List
from redis.exceptions import RedisError

from cheshirecat.db import crud, models
from cheshirecat.db.database import DEFAULT_AGENT_KEY
from cheshirecat.log import log


def format_key(key_id: str) -> str:
    """
    Format Redis key for settings.

    Args:
        key_id: Settings key identifier.

    Returns:
        Formatted key (e.g., "key_id:default_agent").
    """
    return f"{key_id}:{DEFAULT_AGENT_KEY}"


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


def get_settings_by_category(key_id: str, category: str) -> List[Dict]:
    """
    Retrieve settings from Redis filtered by category.

    Args:
        key_id: Settings key identifier.
        category: Category to filter settings.

    Returns:
        List of settings dictionaries, or empty list if none found.

    Raises:
        RedisError: If Redis connection fails.
    """
    if not category:
        log.warning(f"Empty category for {key_id}, returning empty list")
        return []

    try:
        settings: List[Dict] = crud.read(format_key(key_id), path=f'$[?(@.category=="{category}")]')
        if not settings:
            log.debug(f"No settings found for {key_id}, category: {category}")
            return []

        log.debug(f"Retrieved {len(settings)} settings for {key_id}, category: {category}")
        return settings
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
    try:
        settings: List[Dict] = crud.read(format_key(key_id), path=f'$[?(@.name=="{name}")]')
        if not settings:
            log.debug(f"No setting found for {key_id}, name: {name}")
            return None

        log.debug(f"Retrieved setting for {key_id}, name: {name}")
        return settings[0]
    except RedisError as e:
        log.error(f"Redis error getting setting by name for {key_id}: {e}")
        raise


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
    try:
        settings: List[Dict] = crud.read(format_key(key_id), path=f'$[?(@.setting_id=="{setting_id}")]')
        if not settings:
            log.debug(f"No setting found for {key_id}, setting_id: {setting_id}")
            return None

        log.debug(f"Retrieved setting for {key_id}, setting_id: {setting_id}")
        return settings[0]
    except RedisError as e:
        log.error(f"Redis error getting setting by ID for {key_id}: {e}")
        raise


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
