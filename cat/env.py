import os


def get_supported_env_variables():
    return {
        "CCAT_ADMIN_DEFAULT_PASSWORD": "AIBlackBirdWithCheshireCat",
        "CCAT_API_KEY": None,
        "CCAT_DEBUG": "true",
        "CCAT_LOG_LEVEL": "INFO",
        "CCAT_CORS_ALLOWED_ORIGINS": None,
        "CCAT_REDIS_HOST": None,
        "CCAT_REDIS_PORT": "6379",
        "CCAT_REDIS_PASSWORD": "",
        "CCAT_REDIS_DB": "0",
        "CCAT_REDIS_TLS": False,
        "CCAT_RABBITMQ_HOST": None,
        "CCAT_RABBITMQ_PORT": "5672",
        "CCAT_RABBITMQ_USER": "guest",
        "CCAT_RABBITMQ_PASSWORD": "guest",
        "CCAT_RABBITMQ_TLS": False,
        "CCAT_JWT_SECRET": "secret",
        "CCAT_JWT_EXPIRE_MINUTES": str(60 * 24),  # JWT expires after 1 day
        "CCAT_HTTPS_PROXY_MODE": "false",
        "CCAT_CORS_FORWARDED_ALLOW_IPS": "*",
        "CCAT_HISTORY_EXPIRATION": None,  # in minutes
        "CCAT_CORS_ENABLED": "true",
        "CCAT_CRYPTO_KEY": "cheshirecat",
        "CCAT_CRYPTO_SALT": "cheshirecat_salt",
    }


def get_env(name):
    """Utility to get an environment variable value. To be used only for supported Cat envs.
    - covers default supported variables and their default value
    - automagically handles legacy env variables missing the prefix "CCAT_"
    """
    cat_default_env_variables = get_supported_env_variables()

    default = None
    if name in cat_default_env_variables:
        default = cat_default_env_variables[name]

    return os.getenv(name, default)


def get_env_bool(name):
    return get_env(name) in ("1", "true")
