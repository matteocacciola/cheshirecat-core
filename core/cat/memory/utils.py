from typing import Dict, TypeAlias

from pydantic import BaseModel
from qdrant_client.http.models import Record, ScoredPoint, VectorStruct
from langchain_core.documents.base import Document, Blob

from cat.utils import Enum as BaseEnum, BaseModelDict


class ContentType(BaseEnum):
    TEXT = "text"
    IMAGE = "image"
    AUDIO = "audio"


class VectorMemoryCollectionTypes(BaseEnum):
    EPISODIC = "episodic"
    DECLARATIVE = "declarative"
    PROCEDURAL = "procedural"


class VectorEmbedderSize(BaseModel):
    text: int
    image: int | None = None
    audio: int | None = None


class VectorMemoryConfig(BaseModelDict):
    embedder_name: str
    embedder_size: VectorEmbedderSize


class MultimodalContent(BaseModel):
    """Represents multimodal content with optional text, image and audio data"""
    text: str | None = None
    image_url: str | None = None
    audio_url: str | None = None


class DocumentRecallItem(BaseModelDict):
    """
    Langchain `Document` or `Blob` retrieved from the episodic memory, with the similarity score, the vectors for each
    modality and the id of the memory.
    """

    document: Document | Blob
    score: float | None = None
    vector: VectorStruct
    id: str | None = None


DocumentRecall: TypeAlias = Dict[ContentType, DocumentRecallItem]


def to_document_recall(m: Record | ScoredPoint) -> DocumentRecall:
    """
    Convert a Qdrant point to a DocumentRecall object

    Args:
        m: The Qdrant point

    Returns:
        DocumentRecall: The converted DocumentRecall object
    """

    result = {}
    for k, v in m.vector.items():
        doc = Document(
            page_content=m.payload.get("page_content")[str(k)],
            metadata=m.payload.get("metadata", {})
        ) if k == ContentType.TEXT else Blob(
            data=m.payload.get("page_content")[str(k)],
            metadata=m.payload.get("metadata", {})
        )
        item = DocumentRecallItem(
            document=doc,
            vector=v,
            id=m.id,
        )
        if isinstance(m, ScoredPoint):
            item.score = m.score
        result[ContentType(k)] = item

    return result
