from typing import Iterator
from langchain_community.document_loaders import UnstructuredPowerPointLoader
from langchain_core.documents.base import Document, Blob
from langchain.document_loaders.base import BaseBlobParser


class PowerPointParser(BaseBlobParser):
    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        with blob.as_temp_file() as temp_path:
            loader = UnstructuredPowerPointLoader(temp_path)
            documents = loader.load()

        for doc in documents:
            metadata = doc.metadata.copy() if doc.metadata else {}
            metadata.update(blob.metadata or {})

            yield Document(page_content=doc.page_content, metadata=metadata)
