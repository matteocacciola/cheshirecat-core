from typing import List

from cat.core_plugins.multimodality.chunker import ImageChunkerSettings
from cat.core_plugins.multimodality.embedder import EmbedderJinaMultimodalConfig
from cat.factory.chunker import ChunkerSettings
from cat.factory.embedder import EmbedderSettings
from cat.mad_hatter.decorators import hook


@hook(priority=0)
def factory_allowed_chunkers(allowed: List[ChunkerSettings], cat) -> List:
    return allowed + [
        ImageChunkerSettings,
    ]


@hook(priority=0)
def factory_allowed_embedders(allowed: List[EmbedderSettings], cat) -> List:
    return allowed + [
        EmbedderJinaMultimodalConfig,
    ]
