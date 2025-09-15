from typing import Iterator, Type
from langchain_community.document_loaders import UnstructuredFileLoader
from langchain_core.documents.base import Document, Blob
from langchain.document_loaders.base import BaseBlobParser


class UnstructuredParser(BaseBlobParser):
    def __init__(self, document_loader_type: Type[UnstructuredFileLoader]):
        self._document_loader_type = document_loader_type

    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        with blob.as_temp_file() as temp_path:
            loader = self._document_loader_type(temp_path)
            documents = loader.load()

        for doc in documents:
            metadata = doc.metadata.copy() if doc.metadata else {}
            metadata.update(blob.metadata or {})

            yield Document(page_content=doc.page_content, metadata=metadata)
