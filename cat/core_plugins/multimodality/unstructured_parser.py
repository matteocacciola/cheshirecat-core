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

                loader = self._document_loader_type(
                    temp_path,
                    strategy="hi_res",  # or "fast" for born-digital PDFs
                    extract_images_in_pdf=True,
                    infer_table_structure=True,
                    extract_image_block_types=["Image", "Table"],
                )

                # Get raw elements instead of processed documents
                # This gives us access to element.category and element.metadata
                elements = loader._get_elements()  # This is the key change!
                for element in elements:
                    # Build enhanced metadata
                    metadata = blob.metadata.copy() if blob.metadata else {}

                    # Add element type
                    metadata["element_type"] = element.category
                    metadata["has_formula"] = element.category == "Formula"

                    # Extract formula LaTeX if present
                    if element.category == "Formula":
                        # Try different metadata fields where LaTeX might be stored
                        formula_text = (
                                getattr(element.metadata, "text_as_html", None) or
                                getattr(element.metadata, "formula", None) or
                                str(element)
                        )
                        metadata["formula_latex"] = formula_text

                    # Add image data if present
                    if element.category == "Image":
                        # Unstructured stores image data in metadata
                        if hasattr(element.metadata, "image_base64"):
                            metadata["image_data"] = element.metadata.image_base64
                        if hasattr(element.metadata, "image_path"):
                            metadata["image_path"] = element.metadata.image_path

                    # Add table structure if present
                    if element.category == "Table":
                        if hasattr(element.metadata, "text_as_html"):
                            metadata["table_html"] = element.metadata.text_as_html

                    # Preserve coordinates for all elements
                    if hasattr(element.metadata, "coordinates"):
                        metadata["coordinates"] = element.metadata.coordinates

                    # Preserve page number
                    if hasattr(element.metadata, "page_number"):
                        metadata["page_number"] = element.metadata.page_number

                    yield Document(
                        page_content=str(element),
                        metadata=metadata
                    )
            finally:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

    @property
    def document_loader_type(self) -> Type[UnstructuredFileLoader]:
        return self._document_loader_type
