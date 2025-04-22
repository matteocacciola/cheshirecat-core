from abc import ABC, abstractmethod
from typing import List, Iterable
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from cat.chunkers import SemanticChunker as SemanticAnalyzer


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


class TextChunker(BaseChunker):
    def __init__(self, encoding_name: str, chunk_size: int, chunk_overlap: int):
        self._encoding_name = encoding_name
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        return self.analyzer.split_documents(documents)

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


class SemanticChunker(BaseChunker):
    def __init__(self, model_name: str, cluster_threshold: float, similarity_threshold: float, max_tokens: int):
        self._model_name = model_name
        self._cluster_threshold = cluster_threshold
        self._similarity_threshold = similarity_threshold
        self._max_tokens = max_tokens

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        texts = [{"text": doc.page_content, "metadata": doc.metadata} for doc in documents]
        chunks = self.analyzer.chunk(texts)

        return [
            Document(
                page_content=chunk["text"],
                metadata={"source_chunks": chunk.get("metadata", [])}

            )
            for chunk in chunks
        ]

    @property
    def analyzer(self):
        return SemanticAnalyzer(
            model_name=self._model_name,
            cluster_threshold=self._cluster_threshold,
            similarity_threshold=self._similarity_threshold,
            max_tokens=self._max_tokens
        )
