from typing import Type, List, Tuple
from pydantic import ConfigDict

from cat.core_plugins.factories.chunker.custom import (
    SemanticChunker,
    HTMLSemanticChunker,
    JSONChunker,
    TokenSpacyChunker,
    TokenNLTKChunker,
)
from cat.factory.chunker import ChunkerSettings


class SemanticChunkerSettings(ChunkerSettings):
    model_name: str
    cluster_threshold: float = 0.4
    similarity_threshold: float = 0.4
    max_tokens: int = 512

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Semantic chunker",
            "description": "Configuration for semantic chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[SemanticChunker]:
        return SemanticChunker


class HTMLSemanticChunkerSettings(ChunkerSettings):
    headers_to_split_on: List[Tuple[str, str]] | List[List[str]] = [
        ("h1", "Header 1"),
        ("h2", "Header 2"),
    ]
    elements_to_preserve: List[str] = ["table", "ul", "ol", "code"]

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "HTML Semantic chunker",
            "description": "Configuration for HTML semantic chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[HTMLSemanticChunker]:
        return HTMLSemanticChunker


class JSONChunkerSettings(ChunkerSettings):
    max_chunk_size: int = 2000
    min_chunk_size: int | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "JSON Semantic chunker",
            "description": "Configuration for JSON semantic chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[JSONChunker]:
        return JSONChunker


class TokenSpacyChunkerSettings(ChunkerSettings):
    chunk_size: int = 4000
    chunk_overlap: int = 200
    max_length: int = 1_000_000

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "spaCy token-based chunker",
            "description": "Configuration for spaCy token-based chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[TokenSpacyChunker]:
        return TokenSpacyChunker


class TokenNLTKChunkerSettings(ChunkerSettings):
    chunk_size: int = 4000
    chunk_overlap: int = 200
    language: str = "english"

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "NLTK token-based chunker",
            "description": "Configuration for NLTK token-based chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[TokenNLTKChunker]:
        return TokenNLTKChunker
