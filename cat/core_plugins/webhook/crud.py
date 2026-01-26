from typing import Dict, Any
from redis.exceptions import RedisError

from cat.db import crud
from cat.log import log


KEY_PREFIX = "webhooks"


def format_key(agent_id: str, event_id: str) -> str:
    return f"{KEY_PREFIX}:{agent_id}:{event_id}"


def get_webhook(agent_id: str, event: str) -> Dict[str, Any] | None:
    key = format_key(agent_id, event)

    try:
        webhook = crud.read(key)
        if webhook is None:
            log.debug(f"No webhook found for {key.replace(KEY_PREFIX + ':', '')}")
            return None

        if isinstance(webhook, list):
            webhook = webhook[0]

        return webhook
    except RedisError as e:
        log.error(f"Redis error getting webhooks for {key.replace(KEY_PREFIX + ':', '')}: {e}")
        raise


def set_webhook(agent_id: str, event: str, settings: Dict[str, Any]) -> Dict[str, Any]:
    key = format_key(agent_id, event)

    try:
        # Check if the key exists
        existing_data = crud.read(key)

        if existing_data is None:
            existing_data = [settings]
        else:
            existing_data.append(settings)

        # Key exists - update only the messages path
        crud.store(key, existing_data)

        log.debug(f"Stored the URL '{settings['url']}' as a webhook for {key.replace(KEY_PREFIX + ':', '')}")
        return settings
    except (RedisError, ValueError) as e:
        log.error(f"Error storing the URL '{settings['url']}' as a webhook for {key.replace(KEY_PREFIX + ':', '')}: {e}")
        raise


def delete_webhook(agent_id: str, event: str, url: str, secret: str) -> None:
    key = format_key(agent_id, event)

    try:
        settings = crud.read(key) or []
        settings = [
            setting
            for setting in settings
            if settings["url"] not in [url, f"{url}/"] and settings["secret"] != secret
        ]

        crud.store(key, settings)
        log.debug(f"Deleted the URL '{url}' as webhook for {key.replace(KEY_PREFIX + ':', '')}")
    except RedisError as e:
        log.error(f"Redis error deleting the URL '{url}' as webhook for {key.replace(KEY_PREFIX + ':', '')}: {e}")
        raise
