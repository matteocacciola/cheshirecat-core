import asyncio
from abc import ABC, abstractmethod
from typing import Type, List, Iterable, Any
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pydantic import ConfigDict

from cat.services.factory.models import BaseFactoryConfigModel


class BaseChunker(ABC):
    """
    Base class to build custom chunkers. This class is used to create custom chunkers that can be used to split text into
    smaller chunks. The chunkers are used to split text into smaller chunks that can be processed by the model.
    MUST be implemented by subclasses.
    """
    def __init__(self):
        self._splitter = None

    @abstractmethod
    async def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        """
        Split the documents into smaller chunks.
        Implementations that perform CPU-bound work should offload it via
        ``asyncio.to_thread`` to avoid blocking the event loop.

        Args:
            documents: the documents to split

        Returns:
            The list of documents after splitting
        """
        pass

    @abstractmethod
    def _get_splitter(self) -> Any:
        pass

    @property
    def splitter(self):
        if not self._splitter:
            self._splitter = self._get_splitter()
        return self._splitter


class EmbeddedBaseChunker(BaseChunker, ABC):
    async def _ensure_embedder(self):
        from cat.looking_glass.bill_the_lizard import BillTheLizard

        if hasattr(self.splitter, "embedder") and not self.splitter.embedder:
            embedder = await BillTheLizard().embedder()
            self.splitter.embedder = embedder


class RecursiveTextChunker(BaseChunker):
    def __init__(self, encoding_name: str, chunk_size: int, chunk_overlap: int):
        super().__init__()

        self._encoding_name = encoding_name
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def _get_splitter(self) -> RecursiveCharacterTextSplitter:
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

    async def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        docs = list(documents)
        return await asyncio.to_thread(self.splitter.split_documents, docs)


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
