from pydantic import BaseModel

from cat.mad_hatter.decorators import plugin


# Plugin settings
class PluginSettings(BaseModel):
    host: str = "0.0.0.0"
    port: int = 5672
    username: str = "guest"
    password: str = ""
    is_tls: bool = False


@plugin
def settings_schema():
    return PluginSettings.model_json_schema()
