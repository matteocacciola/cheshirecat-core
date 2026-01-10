import redis

from cat.env import get_env
from cat.utils import singleton

DEFAULT_AGENT_KEY = "agent"  # default agent_id for backward compatibility
DEFAULT_SYSTEM_KEY = "system"
DEFAULT_SCHEMA_KEY = "schema"
UNALLOWED_AGENT_KEYS = [
    DEFAULT_SYSTEM_KEY,
    DEFAULT_SCHEMA_KEY,
    "agent_id",
    "chat_id",
    "user_id",
    "session_id",
    "message_id",
    "web",
    "batch",
]


@singleton
class Database:
    def __init__(self):
        self.db = self.get_redis_client()

    def get_redis_client(self) -> redis.Redis:
        host = get_env("CCAT_REDIS_HOST")
        if host is None:
            raise ValueError("CCAT_REDIS_HOST environment variable is not set.")

        password = get_env("CCAT_REDIS_PASSWORD")
        tls = get_env("CCAT_REDIS_TLS")

        if password:
            return redis.Redis(
                host=host,
                port=int(get_env("CCAT_REDIS_PORT")),
                db=get_env("CCAT_REDIS_DB"),
                password=password,
                encoding="utf-8",
                decode_responses=True,
                ssl=tls,
            )

        return redis.Redis(
            host=host,
            port=int(get_env("CCAT_REDIS_PORT")),
            db=get_env("CCAT_REDIS_DB"),
            encoding="utf-8",
            decode_responses=True,
            ssl=tls,
        )

    @property
    def connection_string(self):
        secure = "s" if get_env("CCAT_REDIS_TLS") else ""

        host = get_env("CCAT_REDIS_HOST")
        port = get_env("CCAT_REDIS_PORT")
        db = get_env("CCAT_REDIS_DB")

        password = get_env("CCAT_REDIS_PASSWORD")

        return (
            f"redis{secure}://{host}:{port}/{db}"
            if not password else f"redis{secure}://:{password}@{host}:{port}/{db}"
        )


def get_db() -> redis.Redis:
    return Database().db


def get_db_connection_string() -> str:
    return Database().connection_string
