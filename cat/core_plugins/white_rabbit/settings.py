from pydantic import BaseModel

from cat import plugin


# Plugin settings
class PluginSettings(BaseModel):
    embed_procedures_every_n_days: int = 7


@plugin
def settings_schema():
    return PluginSettings.model_json_schema()
