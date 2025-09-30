import uvicorn

from cat.env import get_env, get_env_bool
from cat.utils import get_base_path, get_plugins_path

# RUN!
if __name__ == "__main__":
    # debugging utilities, to deactivate put `DEBUG=false` in .env
    debug_config = {}
    if get_env_bool("CCAT_DEBUG"):
        debug_config = {
            "reload": True,
            "reload_dirs": [get_base_path()],
            "reload_excludes": [get_plugins_path()],
        }
    # uvicorn running behind an https proxy
    proxy_pass_config = {}
    if get_env_bool("CCAT_HTTPS_PROXY_MODE"):
        proxy_pass_config = {
            "proxy_headers": True,
            "forwarded_allow_ips": get_env("CCAT_CORS_FORWARDED_ALLOW_IPS"),
        }

    uvicorn.run(
        "cat.startup:cheshire_cat_api",
        host="0.0.0.0",
        port=80,
        use_colors=True,
        log_level=get_env("CCAT_LOG_LEVEL").lower(),
        **debug_config,
        **proxy_pass_config,
    )
