import uvicorn

from cheshirecat.env import get_env, get_env_bool
from cheshirecat.utils import get_base_path, get_plugins_path


# RUN!
if __name__ == "__main__":
    # debugging utilities, to deactivate put `DEBUG=false` in .env
    debug_config = {}
    if get_env("CCAT_DEBUG") == "true":
        debug_config = {
            "reload": True,
            "reload_dirs": [
                get_base_path(),
                get_plugins_path()
            ],
        }
    # uvicorn running behind an https proxy
    proxy_pass_config = {}
    if get_env_bool("CCAT_HTTPS_PROXY_MODE"):
        proxy_pass_config = {
            "proxy_headers": True,
            "forwarded_allow_ips": get_env("CCAT_CORS_FORWARDED_ALLOW_IPS"),
        }

    workers = get_env("CCAT_WORKERS")
    if workers:
        workers = int(workers)

    limit_max_requests = get_env("CCAT_LIMIT_MAX_REQUESTS")
    if limit_max_requests:
        limit_max_requests = int(limit_max_requests)

    uvicorn.run(
        "cheshirecat.startup:cheshire_cat_api",
        host="0.0.0.0",
        port=80,
        use_colors=True,
        workers=workers,
        limit_max_requests=limit_max_requests,
        log_level=get_env("CCAT_LOG_LEVEL").lower(),
        **debug_config,
        **proxy_pass_config,
    )
