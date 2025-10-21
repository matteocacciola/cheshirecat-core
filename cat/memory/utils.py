import json
from typing import List, Any, Dict
from langchain_core.documents import Document as LangChainDocument
from pydantic import BaseModel, Field

from cat import utils
from cat.log import log


class VectorMemoryType(utils.Enum):
    DECLARATIVE = "declarative"
    PROCEDURAL = "procedural"


class DocumentRecall(utils.BaseModelDict):
    """
    Langchain `Document` retrieved from a memory, with the similarity score, the list of embeddings and the
    id of the memory.
    """
    document: LangChainDocument
    score: float | None = None
    vector: List[float] = Field(default_factory=list)
    id: str | None = None


class SparseVector(BaseModel, extra="forbid"):
    """
    Sparse vector structure
    """
    indices: List[int] = Field(..., description="Indices must be unique")
    values: List[float] = Field(..., description="Values and indices must be the same length")


class Document(BaseModel, extra="forbid"):
    """
    WARN: Work-in-progress, unimplemented  Text document for embedding. Requires inference infrastructure, unimplemented.
    """
    text: str = Field(..., description="Text of the document This field will be used as input for the embedding model")
    model: str = Field(
        ..., description="Name of the model used to generate the vector List of available models depends on a provider"
    )
    options: Dict[str, Any] | None = Field(
        default=None, description="Parameters for the model Values of the parameters are model-specific"
    )


class Image(BaseModel, extra="forbid"):
    """
    WARN: Work-in-progress, unimplemented  Image object for embedding. Requires inference infrastructure, unimplemented.
    """
    image: Any = Field(..., description="Image data: base64 encoded image or an URL")
    model: str = Field(
        ..., description="Name of the model used to generate the vector List of available models depends on a provider"
    )
    options: Dict[str, Any] | None = Field(
        default=None, description="Parameters for the model Values of the parameters are model-specific"
    )


class InferenceObject(BaseModel, extra="forbid"):
    """
    WARN: Work-in-progress, unimplemented  Custom object for embedding. Requires inference infrastructure, unimplemented.
    """
    object: Any = Field(
        ...,
        description="Arbitrary data, used as input for the embedding model Used if the model requires more than one input or a custom input",
    )
    model: str = Field(
        ..., description="Name of the model used to generate the vector List of available models depends on a provider"
    )
    options: Dict[str, Any] | None = Field(
        default=None, description="Parameters for the model Values of the parameters are model-specific"
    )


Vector = List[float] | SparseVector | List[List[float]] | Document | Image | InferenceObject
VectorOutput = List[float] | List[List[float]] | Dict[str, List[float] | List[List[float]] | SparseVector]
VectorStruct = List[float] | List[List[float]] | Dict[str, Vector] | Document | Image | InferenceObject
VectorStructOutput = List[float] | List[List[float]] | Dict[str, VectorOutput]
Payload = Dict[str, Any]


class Record(BaseModel):
    """
    Point data
    """
    id: int | str = Field(..., description="Point data")
    payload: Payload | None = Field(default=None, description="Payload - values assigned to the point")
    vector: VectorStructOutput | None = Field(default=None, description="Vector of the point")
    shard_key: int | str | None = Field(default=None, description="Shard Key")
    order_value: int | float | None = Field(default=None, description="Point data")


class ScoredPoint(BaseModel):
    """
    Search result
    """
    id: int | str = Field(..., description="Search result")
    version: int = Field(..., description="Point version")
    score: float = Field(..., description="Points vector distance to the query vector")
    payload: Payload | None = Field(default=None, description="Payload - values assigned to the point")
    vector: VectorStructOutput | None = Field(default=None, description="Vector of the point")
    shard_key: int | str | None = Field(default=None, description="Shard Key")
    order_value: int | float | None = Field(default=None, description="Order-by value")


class PointStruct(BaseModel, extra="forbid"):
    id: int | str = Field(..., description="")
    vector: VectorStruct = Field(..., description="")
    payload: Payload | None = Field(default=None, description="Payload values (optional)")


class UpdateResult(BaseModel):
    operation_id: int = Field(default=None, description="Sequential number of the operation")
    status: str = Field(..., description="")


class RecallSettings(utils.BaseModelDict):
    embedding: List[float] = Field(default_factory=list)
    k: int | None = 3
    latest_n_history: int | None = 3
    threshold: float | None = 0.5
    metadata: dict | None = None


async def recall(
    cat: "StrayCat",
    query: List[float],
    collection: VectorMemoryType,
    k: int | None = 5,
    threshold: int | None = None,
    metadata: Dict | None = None,
) -> List[DocumentRecall]:
    """
    This is a proxy method to perform search in a vector memory collection.
    The method allows retrieving information from one specific vector memory collection with custom parameters.
    The Cat uses this method internally to recall the relevant memories to Working Memory every user's chat
    interaction.
    This method is useful also to perform a manual search in hook and tools.

    Args:
        cat (StrayCat): The StrayCat instance.
        query (List[float]): The search query, passed as embedding vector. Please first run cheshire_cat.embedder.embed_query(query) if you have a string query to pass here.
        collection (VectorMemoryType): The name of the vector memory collection to retrieve memories from.
        k (int | None): The number of memories to retrieve. If `None` retrieves all the available memories.
        threshold (float | None): The minimum similarity to retrieve a memory. Memories with lower similarity are ignored.
        metadata (Dict): Additional filter to retrieve memories with specific metadata.

    Returns:
        memories (List[DocumentRecall]): List of retrieved memories.
    """
    cheshire_cat = cat.cheshire_cat

    if k:
        memories = await cheshire_cat.vector_memory_handler.recall_memories_from_embedding(
            str(collection), query, metadata, k, threshold
        )
        return memories

    memories = await cheshire_cat.vector_memory_handler.recall_all_memories(str(VectorMemoryType.DECLARATIVE))
    return memories


async def recall_relevant_memories_to_working_memory(cat: "StrayCat", collection: VectorMemoryType, query: str) -> List[DocumentRecall]:
    """
    Retrieve context from memory.
    The method retrieves the relevant memories from the vector collections that are given as context to the LLM.
    Recalled memories are stored in the working memory.

    Args:
        cat (StrayCat): The StrayCat instance.
        collection (VectorMemoryType): The name of the vector memory collection to retrieve memories from.
        query (str): The query used to make a similarity search in the Cat's vector memories.

    See Also:
        cat_recall_query
        before_cat_recalls_memories
        after_cat_recalls_memories

    Examples
    --------
    Recall memories from a custom query
    >> cat.recall_relevant_memories_to_working_memory(query="What was written on the bottle?")

    Notes
    -----
    The user's message is used as a query to make a similarity search in the Cat's vector memories.
    Five hooks allow customizing the recall pipeline before and after it is done.
    """
    cheshire_cat = cat.cheshire_cat
    plugin_manager = cat.plugin_manager

    # We may want to search in memory. If a query is not provided, use the user's message as the query
    recall_query = plugin_manager.execute_hook("cat_recall_query", query, cat=cat)
    log.info(f"Agent id: {cat.agent_id}. Recall query: '{recall_query}'")

    # keep track of embedder model usage
    cat.working_memory.recall_query = recall_query

    # Setting default recall configs for each memory + hooks to change recall configs for each memory
    config = RecallSettings(
        embedding=cheshire_cat.embedder.embed_query(recall_query),
        metadata=cat.working_memory.user_message.get("metadata", {}),
    )

    # hook to do something before recall begins
    config = utils.restore_original_model(
        plugin_manager.execute_hook("before_cat_recalls_memories", config, cat=cat),
        RecallSettings
    )
    cat.latest_n_history = config.latest_n_history

    memories = await recall(
        cat=cat,
        query=config.embedding,
        k=config.k,
        threshold=config.threshold,
        metadata=config.metadata,
        collection=collection,
    )

    # hook to modify/enrich retrieved memories
    plugin_manager.execute_hook("after_cat_recalls_memories", cat=cat)

    return memories


def to_document_recall(m: Record | ScoredPoint) -> DocumentRecall:
    """
    Convert a Qdrant point to a DocumentRecall object

    Args:
        m (Record | ScoredPoint): The Qdrant point

    Returns:
        DocumentRecall: The converted DocumentRecall object
    """
    page_content = m.payload.get("page_content", "") if m.payload else ""
    if isinstance(page_content, dict):
        page_content = json.dumps(page_content)

    metadata = m.payload.get("metadata", {}) if m.payload else {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}

    document = DocumentRecall(
        document=LangChainDocument(
            page_content=page_content,
            metadata=metadata,
        ),
        vector=m.vector,
        id=m.id,
    )

    if isinstance(m, ScoredPoint):
        document.score = m.score

    return document
