from abc import ABC, abstractmethod
from typing import Type, List, Iterable
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import ConfigDict

from cat.services.factory.base_factory import BaseFactory, BaseFactoryConfigModel


class BaseChunker(ABC):
    """
    Base class to build custom chunkers. This class is used to create custom chunkers that can be used to split text into
    smaller chunks. The chunkers are used to split text into smaller chunks that can be processed by the model.
    MUST be implemented by subclasses.
    """
    @abstractmethod
    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        """
        Split the documents into smaller chunks.

        Args:
            documents: the documents to split

        Returns:
            The list of documents after splitting
        """
        pass

    @property
    @abstractmethod
    def analyzer(self):
        pass


class RecursiveTextChunker(BaseChunker):
    def __init__(self, encoding_name: str, chunk_size: int, chunk_overlap: int):
        self._encoding_name = encoding_name
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    @property
    def analyzer(self):
        return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=self._chunk_size,
            chunk_overlap=self._chunk_overlap,
            separators=["\\n\\n", "\n\n", ".\\n", ".\n", "\\n", "\n", " ", ""],
            encoding_name=self._encoding_name,
            keep_separator=True,
            strip_whitespace=True,
            allowed_special={"\n"},  # Explicitly allow the special token ‘\n’
            disallowed_special=(),  # Disallow control for other special tokens
        )

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        return self.analyzer.split_documents(documents)



class ChunkerSettings(BaseFactoryConfigModel, ABC):
    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type[BaseChunker]:
        return BaseChunker

    @classmethod
    @abstractmethod
    def pyclass(cls) -> Type[BaseChunker]:
        pass


class RecursiveTextChunkerSettings(ChunkerSettings):
    encoding_name: str = "cl100k_base"
    chunk_size: int = 256
    chunk_overlap: int = 64

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Recursive text splitter",
            "description": "Configuration for a recursive text splitter to be used to split text into smaller chunks",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[RecursiveTextChunker]:
        return RecursiveTextChunker


class ChunkerFactory(BaseFactory):
    @property
    def factory_allowed_handler_name(self) -> str:
        return "factory_allowed_chunkers"

    @property
    def setting_category(self) -> str:
        return "chunker"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return RecursiveTextChunkerSettings

    @property
    def schema_name(self) -> str:
        return "chunkerName"
