import json
import pandas as pd
from typing import Iterator
from langchain_core.documents import Document
from langchain.document_loaders.base import BaseBlobParser
from langchain.document_loaders.blob_loaders.schema import Blob


class TableParser(BaseBlobParser):
    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        with blob.as_bytes_io() as file:
            if blob.mimetype == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
                content = pd.read_excel(file, index_col=0)
            elif blob.mimetype == "text/csv":
                content = pd.read_csv(file, index_col=0)

        content = content.to_dict()

        yield Document(page_content=json.dumps(content), metadata={})
