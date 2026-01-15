from typing import List, Any, Dict
from langchain_core.documents import Document as LangChainDocument
from pydantic import BaseModel, Field

from cat import utils


class VectorMemoryType(utils.Enum):
    DECLARATIVE = "declarative"
    PROCEDURAL = "procedural"


class DocumentRecall(BaseModel):
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
    Text document for embedding.
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
    id: int | str | None = Field(..., description="")
    vector: VectorStruct = Field(..., description="")
    payload: Payload | None = Field(default=None, description="Payload values (optional)")


class UpdateResult(BaseModel):
    operation_id: int = Field(default=None, description="Sequential number of the operation")
    status: str = Field(..., description="")


class RecallSettings(BaseModel):
    embedding: List[float]
    k: int | None = 5
    latest_n_history: int | None = 3
    threshold: float | None = 0.5
    metadata: Dict[str, Any] | None = None
