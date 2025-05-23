import json
from typing import Iterator
from langchain_core.documents import Document
from langchain.document_loaders.base import BaseBlobParser
from langchain.document_loaders.blob_loaders.schema import Blob


class JSONParser(BaseBlobParser):
    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        with blob.as_bytes_io() as file:
            text = json.load(file)
        yield Document(page_content=text, metadata={})
