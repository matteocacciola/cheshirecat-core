from typing import Iterator
from langchain_community.document_loaders import UnstructuredPowerPointLoader
from langchain_core.documents import Document
from langchain.document_loaders.base import BaseBlobParser
from langchain.document_loaders.blob_loaders.schema import Blob


class PowerPointParser(BaseBlobParser):
    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        with blob.as_temp_file() as temp_path:
            loader = UnstructuredPowerPointLoader(temp_path)
            documents = loader.load()

        for doc in documents:
            metadata = doc.metadata.copy() if doc.metadata else {}
            metadata.update(blob.metadata or {})

            yield Document(page_content=doc.page_content, metadata=metadata)
