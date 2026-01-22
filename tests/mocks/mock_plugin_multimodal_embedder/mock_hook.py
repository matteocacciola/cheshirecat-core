from typing import Type, List
from pydantic import ConfigDict

from cat import hook, EmbedderSettings, EmbedderMultimodalSettings
from cat.services.factory.embedder import DumbEmbedder


class DumbMultimodalEmbedder(DumbEmbedder):
    pass


class EmbedderMultimodalDumbConfig(EmbedderMultimodalSettings):
    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Multimodal Dumb Embedder",
            "description": "Configuration for multimodal dumb embedder",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return DumbMultimodalEmbedder


@hook(priority=0)
def factory_allowed_embedders(allowed: List[EmbedderSettings], lizard) -> List:
    return allowed + [
        EmbedderMultimodalDumbConfig,
    ]
