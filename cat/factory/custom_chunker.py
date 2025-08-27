import json
from abc import ABC, abstractmethod
from typing import List, Iterable, Tuple
from langchain_core.documents import Document
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter,
    HTMLSemanticPreservingSplitter,
    RecursiveJsonSplitter,
    SpacyTextSplitter,
    NLTKTextSplitter,
)


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


class SemanticChunker(BaseChunker):
    def __init__(self, model_name: str, cluster_threshold: float, similarity_threshold: float, max_tokens: int):
        self._model_name = model_name
        self._cluster_threshold = cluster_threshold
        self._similarity_threshold = similarity_threshold
        self._max_tokens = max_tokens

    @property
    def analyzer(self):
        return SemanticAnalyzer(
            model_name=self._model_name,
            cluster_threshold=self._cluster_threshold,
            similarity_threshold=self._similarity_threshold,
            max_tokens=self._max_tokens
        )

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


class HTMLSemanticChunker(BaseChunker):
    def __init__(
        self, headers_to_split_on: List[Tuple[str, str]] | List[List[str]], elements_to_preserve: List[str]
    ):
        self._headers_to_split_on = headers_to_split_on if isinstance(headers_to_split_on[0], tuple) else [
            (header, header) for header in headers_to_split_on
        ]
        self._elements_to_preserve = elements_to_preserve

    @property
    def analyzer(self):
        return HTMLSemanticPreservingSplitter(
            headers_to_split_on=self._headers_to_split_on,
            separators=["\n\n", "\n", ". ", "! ", "? "],
            max_chunk_size=50,
            preserve_images=True,
            preserve_videos=True,
            elements_to_preserve=self._elements_to_preserve,
            denylist_tags=["script", "style", "head"],
        )

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        return [chunk for doc in documents for chunk in self.analyzer.split_text(doc.page_content)]


class JSONChunker(BaseChunker):
    def __init__(self, max_chunk_size: int, min_chunk_size: int | None = None):
        self._max_chunk_size = max_chunk_size
        self._min_chunk_size = min_chunk_size

    @property
    def analyzer(self):
        return RecursiveJsonSplitter(max_chunk_size=self._max_chunk_size, min_chunk_size=self._min_chunk_size)

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        texts = [json.loads(doc.page_content) for doc in documents]
        metadata = [doc.metadata for doc in documents]
        return self.analyzer.create_documents(texts, metadatas=metadata)


class TokenSpacyChunker(BaseChunker):
    def __init__(self, chunk_size: int, chunk_overlap: int, max_length: int):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._max_length = max_length

    @property
    def analyzer(self):
        return SpacyTextSplitter(
            chunk_size=self._chunk_size, chunk_overlap=self._chunk_overlap, max_length=self._max_length
        )

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        return self.analyzer.split_documents(documents)


class TokenNLTKChunker(BaseChunker):
    def __init__(self, chunk_size: int, chunk_overlap: int, language: str):
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._language = language

    @property
    def analyzer(self):
        return NLTKTextSplitter(
            chunk_size=self._chunk_size, chunk_overlap=self._chunk_overlap, language=self._language
        )

    def split_documents(self, documents: Iterable[Document]) -> List[Document]:
        return self.analyzer.split_documents(documents)
