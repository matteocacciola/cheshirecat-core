import tempfile
import os
from typing import Iterator, Type, Any
import numpy as np
from langchain_community.document_loaders import UnstructuredFileLoader
from langchain_core.document_loaders import BaseBlobParser
from langchain_core.documents.base import Document, Blob


class UnstructuredParser(BaseBlobParser):
    def __init__(self, document_loader_type: Type[UnstructuredFileLoader]):
        self._document_loader_type = document_loader_type

    @staticmethod
    def _serialize_metadata_value(value: Any) -> Any:
        """Convert non-serializable values to JSON-compatible format."""
        # Handle None
        if value is None:
            return None

        # Handle numpy types
        if isinstance(value, (np.integer, np.floating)):
            return float(value)

        # Handle numpy arrays
        if isinstance(value, np.ndarray):
            return value.tolist()

        # Handle tuples (convert to lists for JSON compatibility)
        if isinstance(value, tuple):
            return [UnstructuredParser._serialize_metadata_value(item) for item in value]

        # Handle lists
        if isinstance(value, list):
            return [UnstructuredParser._serialize_metadata_value(item) for item in value]

        # Handle dicts
        if isinstance(value, dict):
            return {k: UnstructuredParser._serialize_metadata_value(v) for k, v in value.items()}

        # Handle objects with __dict__ (like CoordinatesMetadata)
        if hasattr(value, '__dict__'):
            serialized = {}
            for k, v in value.__dict__.items():
                if not k.startswith('_'):  # Skip private attributes
                    try:
                        serialized[k] = UnstructuredParser._serialize_metadata_value(v)
                    except (TypeError, ValueError):
                        # If serialization fails, convert to string
                        serialized[k] = str(v)
            return serialized

        # Handle other basic types
        if isinstance(value, (str, int, float, bool)):
            return value

        # For everything else, convert to string as fallback
        return str(value)

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
                elements = loader._get_elements()

                for element in elements:
                    # Build enhanced metadata
                    metadata = blob.metadata.copy() if blob.metadata else {}

                    # Add element type
                    metadata["element_type"] = element.category
                    metadata["has_formula"] = element.category == "Formula"

                    # Extract formula LaTeX if present
                    if element.category == "Formula":
                        formula_text = (
                                getattr(element.metadata, "text_as_html", None) or
                                getattr(element.metadata, "formula", None) or
                                str(element)
                        )
                        metadata["formula_latex"] = formula_text

                    # Add image data if present
                    if element.category == "Image":
                        if hasattr(element.metadata, "image_base64"):
                            metadata["image_data"] = element.metadata.image_base64
                        if hasattr(element.metadata, "image_path"):
                            metadata["image_path"] = element.metadata.image_path

                    # Add table structure if present
                    if element.category == "Table":
                        if hasattr(element.metadata, "text_as_html"):
                            metadata["table_html"] = element.metadata.text_as_html

                    # Preserve coordinates for all elements (SERIALIZED)
                    if hasattr(element.metadata, "coordinates"):
                        metadata["coordinates"] = self._serialize_metadata_value(
                            element.metadata.coordinates
                        )

                    # Preserve page number
                    if hasattr(element.metadata, "page_number"):
                        metadata["page_number"] = int(element.metadata.page_number)

                    # Serialize the entire metadata dict to catch any other problematic values
                    metadata = self._serialize_metadata_value(metadata)

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
