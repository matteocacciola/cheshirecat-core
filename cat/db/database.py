from typing import Dict

import redis.asyncio as aioredis

from cat.env import get_env, get_env_int, get_env_bool
from cat.utils import singleton

DEFAULT_AGENTS_KEY = "agents"
DEFAULT_AGENT_KEY = "agent"
DEFAULT_CONVERSATIONS_KEY = "conversations"
DEFAULT_PLUGINS_KEY = "plugins"
DEFAULT_USERS_KEY = "users"
DEFAULT_SYSTEM_KEY = "system"


@singleton
class Database:
    def __init__(self):
        self.db = self.get_redis_client()

    def get_redis_client(self) -> aioredis.Redis:
        return aioredis.Redis(**get_redis_kwargs())


def get_db() -> aioredis.Redis:
    return Database().db


def get_db_connection_string() -> str:
    secure = "s" if get_env_bool("CAT_REDIS_TLS") else ""

    host = get_env("CAT_REDIS_HOST")
    port = get_env("CAT_REDIS_PORT")
    db = get_env_int("CAT_REDIS_DB")

    password = get_env("CAT_REDIS_PASSWORD")

    return (
        f"redis{secure}://{host}:{port}/{db}"
        if not password else f"redis{secure}://:{password}@{host}:{port}/{db}"
    )

def get_redis_kwargs() -> Dict:
    host = get_env("CAT_REDIS_HOST")
    if host is None:
        raise ValueError("CAT_REDIS_HOST environment variable is not set.")

    password = get_env("CAT_REDIS_PASSWORD")
    tls = get_env_bool("CAT_REDIS_TLS")

    kwargs = dict(
        host=host,
        port=get_env_int("CAT_REDIS_PORT"),
        db=get_env_int("CAT_REDIS_DB"),
        encoding="utf-8",
        decode_responses=True,
        ssl=tls,
    )
    if password:
        kwargs["password"] = password

    return kwargs