from typing import Literal, List
from langchain_core.tools import StructuredTool
from pydantic import Field
import tiktoken

from cat.core_plugins.utils import recall
from cat.factory.vector_db import VectorMemoryType
from cat.looking_glass import HumptyDumpty
from cat.mad_hatter.decorators import hook
from cat.memory.interactions import ModelInteraction
from cat.utils import get_caller_info


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
def before_cat_recalls_memories(cat) -> None:
    message = cat.working_memory.recall_query
    cat.working_memory.model_interactions.append(
        EmbedderModelInteraction(
            prompt=[message],
            source=get_caller_info(skip=1),
            input_tokens=len(tiktoken.get_encoding("cl100k_base").encode(message)),
        )
    )


@hook(priority=1)
def pick_tools_from_memory(tools: List[StructuredTool], cat) -> List[StructuredTool]:
    recall_query = cat.working_memory.recall_query
    embedding = cat.embedder.embed_query(recall_query)

    memories = HumptyDumpty.run_sync_or_async(
        recall,
        cat=cat,
        query=embedding,
        collection=VectorMemoryType.PROCEDURAL,
    )
    return [t for memory in memories for t in tools if t.name == memory.document.metedata.get("source")]
