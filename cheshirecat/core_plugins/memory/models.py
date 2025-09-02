from typing import Literal, List
from pydantic import Field

from cheshirecat import utils
from cheshirecat.memory.interactions import ModelInteraction


class EmbedderModelInteraction(ModelInteraction):
    """
    Represents an interaction with an embedding model.

    Inherits from ModelInteraction and includes attributes specific to embedding interactions.

    Attributes
    ----------
    model_type : Literal["embedder"]
        The type of model, which is fixed to "embedder".
    source : str
        The source of the interaction, defaulting to "recall".
    """
    model_type: Literal["embedder"] = Field(default="embedder")
    source: str = Field(default="recall")


class RecallSettings(utils.BaseModelDict):
    embedding: List[float]
    k: int | None = 3
    threshold: float | None = 0.5
    metadata: dict | None = None