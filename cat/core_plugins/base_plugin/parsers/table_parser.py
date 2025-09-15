import json
from typing import Iterator
import pandas as pd
from langchain.document_loaders.base import BaseBlobParser
from langchain_core.documents.base import Document, Blob


class TableParser(BaseBlobParser):
    def lazy_parse(self, blob: Blob) -> Iterator[Document]:
        excel_mime_types = [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.ms-excel"
        ]

        with blob.as_bytes_io() as file:
            if blob.mimetype in excel_mime_types:
                content = pd.read_excel(file, index_col=0)
            elif blob.mimetype == "text/csv":
                content = pd.read_csv(file, index_col=0)

        content = content.to_dict()

        yield Document(page_content=json.dumps(content), metadata={})
