from typing import Literal, Dict
from pydantic import Field
import tiktoken

from cat import hook, get_caller_info
from cat.services.memory.interactions import ModelInteraction


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


@hook(priority=1)
def before_cat_recalls_memories(config: Dict, cat) -> None:
    message = cat.working_memory.recall_query
    cat.working_memory.model_interactions.add(
        EmbedderModelInteraction(
            prompt=[message],
            source=get_caller_info(skip=1),
            input_tokens=len(tiktoken.get_encoding("cl100k_base").encode(message)),
        )
    )
