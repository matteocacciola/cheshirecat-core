from typing import Dict, Any, List
from redis.exceptions import RedisError

from cat.db import crud
from cat.db.cruds import settings as crud_settings
from cat.db.database import DEFAULT_AGENTS_KEY, DEFAULT_SYSTEM_KEY, DEFAULT_PLUGINS_KEY
from cat.log import log


def format_key(agent_id: str, plugin_id: str) -> str:
    """
    Format Redis key for a plugin's settings.

    Args:
        agent_id: ID of the chatbot.
        plugin_id: ID of the plugin.

    Returns:
        Formatted key (e.g., "agents:<agent_id>:plugins:<plugin_id>" or "system:plugins:<plugin_id>" for the system agent)
    """
    return (
        f"{DEFAULT_SYSTEM_KEY}:{DEFAULT_PLUGINS_KEY}:{plugin_id}"
        if agent_id == DEFAULT_SYSTEM_KEY
        else f"{DEFAULT_AGENTS_KEY}:{agent_id}:{DEFAULT_PLUGINS_KEY}:{plugin_id}"
    )


def get_settings(agent_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Retrieve all plugin settings for a specific agent from Redis.

    Args:
        agent_id: ID of the chatbot.
    Returns:
        Dictionary of plugin settings, or empty dict if none found.
    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        all_settings = crud.read(format_key(agent_id, "*"))
        if not all_settings:
            log.debug(f"No plugin settings found for agent {agent_id}")
            return {}

        if isinstance(all_settings, list):
            all_settings = all_settings[0]

        return all_settings
    except RedisError as e:
        log.error(f"Redis error getting all settings for agent {agent_id}: {e}")
        raise


def get_setting(agent_id: str, plugin_id: str) -> Dict[str, Any] | None:
    """
    Retrieve plugin settings from Redis.

    Args:
        agent_id: ID of the chatbot.
        plugin_id: ID of the plugin.

    Returns:
        Dictionary of plugin settings, or None if not found.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        settings = crud.read(format_key(agent_id, plugin_id))
        if settings is None:
            log.debug(f"No settings found for {agent_id}:{plugin_id}")
            return None

        if isinstance(settings, list):
            settings = settings[0]

        return settings
    except RedisError as e:
        log.error(f"Redis error getting settings for {agent_id}:{plugin_id}: {e}")
        raise


def set_setting(agent_id: str, plugin_id: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Store plugin settings in Redis.

    Args:
        agent_id: ID of the chatbot.
        plugin_id: ID of the plugin.
        settings: Dictionary of plugin settings.

    Returns:
        Stored settings.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If settings serialization fails.
    """
    try:
        crud.store(format_key(agent_id, plugin_id), settings)

        log.debug(f"Stored settings for {agent_id}:{plugin_id}")
        return settings
    except (RedisError, ValueError) as e:
        log.error(f"Error storing settings for {agent_id}:{plugin_id}: {e}")
        raise


def update_setting(agent_id: str, plugin_id: str, updated_settings: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update plugin settings in Redis atomically.

    Args:
        agent_id: ID of the chatbot.
        plugin_id: ID of the plugin.
        updated_settings: Dictionary with settings to update.

    Returns:
        Updated settings.

    Raises:
        RedisError: If Redis connection fails.
        ValueError: If serialization fails.
    """
    try:
        settings_db = get_setting(agent_id, plugin_id) or {}
        settings_db.update(updated_settings)

        return set_setting(agent_id, plugin_id, settings_db)
    except (RedisError, ValueError) as e:
        log.error(f"Error updating settings for {agent_id}:{plugin_id}: {e}")
        raise


def delete_setting(agent_id: str, plugin_id: str):
    """
    Delete plugin settings from Redis.

    Args:
        agent_id: ID of the chatbot.
        plugin_id: ID of the plugin.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.delete(format_key(agent_id, plugin_id))
        log.debug(f"Deleted settings for {agent_id}:{plugin_id}")
    except RedisError as e:
        log.error(f"Redis error deleting settings for {agent_id}:{plugin_id}: {e}")
        raise


def destroy_all(agent_id: str):
    """
    Delete all plugin settings for a specific agent.

    Args:
        agent_id: ID of the chatbot.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.destroy(format_key(agent_id, "*"))
        log.debug(f"Destroyed plugin settings for {agent_id}")
    except RedisError as e:
        log.error(f"Redis error destroying settings for {agent_id}: {e}")
        raise


def destroy_plugin(plugin_id: str):
    """
    Delete all settings for a specific plugin across all agents.

    Args:
        plugin_id: ID of the plugin.

    Raises:
        RedisError: If Redis connection fails.
    """
    try:
        crud.destroy(format_key("*", plugin_id))
        log.debug(f"Destroyed plugin settings for plugin {plugin_id}")
    except RedisError as e:
        log.error(f"Redis error destroying settings for plugin {plugin_id}: {e}")
        raise


def get_agents_plugin_keys(plugin_id: str) -> List[str]:
    """
    Get all unique agent IDs from Redis keys that have the format agents:*:plugin_id:<plugin_name>.

    Args:
        plugin_id: The name of the plugin to filter by.

    Returns:
        List of unique agent IDs that have keys matching the plugin format.

    Raises:
        RedisError: If Redis connection fails.
    """
    pattern = format_key("*", plugin_id)
    return crud_settings.get_agents_main_keys(pattern)


def get_active_plugins_from_db(agent_id: str) -> List[str]:
    """
    Retrieve the list of active plugins for a specific agent from settings.

    Args:
        agent_id: ID of the chatbot.

    Returns:
        List of active plugin IDs.
    """
    active_plugins_from_db = crud_settings.get_setting_by_name(agent_id, "active_plugins")
    active_plugins: List[str] = [] if active_plugins_from_db is None else active_plugins_from_db["value"]
    return active_plugins
