import tempfile
import os
from typing import Iterator, Type
from langchain_community.document_loaders import UnstructuredFileLoader
from langchain_core.document_loaders import BaseBlobParser
from langchain_core.documents.base import Document, Blob


class UnstructuredParser(BaseBlobParser):
    def __init__(self, document_loader_type: Type[UnstructuredFileLoader]):
        self._document_loader_type = document_loader_type

    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        suffix = os.path.splitext(blob.source)[1] if blob.source else ""

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            try:
                temp_file.write(blob.as_bytes())
                temp_file.flush()
                temp_path = temp_file.name

                loader = self._document_loader_type(temp_path)
                documents = loader.load()

                for doc in documents:
                    metadata = doc.metadata.copy() if doc.metadata else {}
                    metadata.update(blob.metadata or {})

                    yield Document(page_content=doc.page_content, metadata=metadata)
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    @property
    def document_loader_type(self) -> Type[UnstructuredFileLoader]:
        return self._document_loader_type
