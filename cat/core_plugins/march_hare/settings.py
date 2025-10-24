from pydantic import BaseModel

from cat import plugin


# Plugin settings
class PluginSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 5672
    username: str = "guest"
    password: str = "guest"
    is_tls: bool = False
    is_disabled: bool = True


@plugin
def settings_schema():
    return PluginSettings.model_json_schema()
