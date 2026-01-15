from pydantic import BaseModel

from cat import plugin


# Plugin settings
class PluginSettings(BaseModel):
    enable_llm_knowledge: bool = True


@plugin
def settings_schema():
    return PluginSettings.model_json_schema()
