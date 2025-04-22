from abc import ABC
from typing import Type, List
from pydantic import ConfigDict

from cat.factory.base_factory import BaseFactory, BaseFactoryConfigModel
from cat.factory.custom_chunker import BaseChunker, TextChunker, SemanticChunker


class ChunkerSettings(BaseFactoryConfigModel, ABC):
    # class instantiating the chunker
    _pyclass: Type[BaseChunker] = None

    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type:
        return BaseChunker


class TextChunkerSettings(ChunkerSettings):
    encoding_name: str = "cl100k_base"
    chunk_size: int = 256
    chunk_overlap: int = 64

    _pyclass: Type = TextChunker

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Text splitter",
            "description": "Configuration for text splitter to be used to split text into smaller chunks",
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


class ChunkerFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[ChunkerSettings]]:
        list_chunkers_default = [
            TextChunkerSettings,
            SemanticChunkerSettings,
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
        return TextChunkerSettings

    @property
    def schema_name(self) -> str:
        return "chunkerName"
