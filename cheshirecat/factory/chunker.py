from abc import ABC
from typing import Type, List, Tuple
from pydantic import ConfigDict

from cheshirecat.factory.base_factory import BaseFactory, BaseFactoryConfigModel
from cheshirecat.factory.custom_chunker import (
    BaseChunker,
    RecursiveTextChunker,
    SemanticChunker,
    HTMLSemanticChunker,
    JSONChunker,
    TokenSpacyChunker,
    TokenNLTKChunker,
)


class ChunkerSettings(BaseFactoryConfigModel, ABC):
    # class instantiating the chunker
    _pyclass: Type[BaseChunker] = None

    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type:
        return BaseChunker


class RecursiveTextChunkerSettings(ChunkerSettings):
    encoding_name: str = "cl100k_base"
    chunk_size: int = 256
    chunk_overlap: int = 64

    _pyclass: Type = RecursiveTextChunker

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Recursive text splitter",
            "description": "Configuration for a recursive text splitter to be used to split text into smaller chunks",
            "link": "",
        }
    )


class SemanticChunkerSettings(ChunkerSettings):
    model_name: str
    cluster_threshold: float = 0.4
    similarity_threshold: float = 0.4
    max_tokens: int = 512

    _pyclass: Type = SemanticChunker

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Semantic chunker",
            "description": "Configuration for semantic chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )


class HTMLSemanticChunkerSettings(ChunkerSettings):
    headers_to_split_on: List[Tuple[str, str]] | List[List[str]] = [
        ("h1", "Header 1"),
        ("h2", "Header 2"),
    ]
    elements_to_preserve: List[str] = ["table", "ul", "ol", "code"]

    _pyclass: Type = HTMLSemanticChunker

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "HTML Semantic chunker",
            "description": "Configuration for HTML semantic chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )


class JSONChunkerSettings(ChunkerSettings):
    max_chunk_size: int = 2000
    min_chunk_size: int | None = None

    _pyclass: Type = JSONChunker

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "JSON Semantic chunker",
            "description": "Configuration for JSON semantic chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )


class TokenSpacyChunkerSettings(ChunkerSettings):
    chunk_size: int = 4000
    chunk_overlap: int = 200
    max_length: int = 1_000_000

    _pyclass: Type = TokenSpacyChunker

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "spaCy token-based chunker",
            "description": "Configuration for spaCy token-based chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )


class TokenNLTKChunkerSettings(ChunkerSettings):
    chunk_size: int = 4000
    chunk_overlap: int = 200
    language: str = "english"

    _pyclass: Type = TokenNLTKChunker

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "NLTK token-based chunker",
            "description": "Configuration for NLTK token-based chunker to be used to split text into smaller chunks",
            "link": "",
        }
    )

class ChunkerFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[ChunkerSettings]]:
        list_chunkers_default = [
            RecursiveTextChunkerSettings,
            SemanticChunkerSettings,
            HTMLSemanticChunkerSettings,
            JSONChunkerSettings,
            TokenSpacyChunkerSettings,
            TokenNLTKChunkerSettings,
        ]

        list_chunkers_default = self._hook_manager.execute_hook(
            "factory_allowed_chunkers", list_chunkers_default, cat=None
        )
        return list_chunkers_default

    @property
    def setting_name(self) -> str:
        return "chunker_selected"

    @property
    def setting_category(self) -> str:
        return "chunker"

    @property
    def setting_factory_category(self) -> str:
        return "chunker_factory"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return RecursiveTextChunkerSettings

    @property
    def schema_name(self) -> str:
        return "chunkerName"
