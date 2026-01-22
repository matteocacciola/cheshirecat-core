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
        temp_path = None

        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
                temp_path = temp_file.name
                temp_file.write(blob.as_bytes())

            loader = self._document_loader_type(
                temp_path,
                strategy="hi_res",
                extract_images_in_pdf=True,
                infer_table_structure=True,
                extract_image_block_types=["Image", "Table"],
            )

            # Accessing raw elements can return items with None text
            elements = loader._get_elements()

            for element in elements:
                # 1. Extract core attributes safely
                element_meta = getattr(element, "metadata", None)
                category = getattr(element, "category", "Uncategorized")
                raw_text = getattr(element, "text", None)
                text_as_html = getattr(element_meta, "text_as_html", None)

                # 2. Content Selection Strategy (Optimized for CLIP/Jina AI)
                # We determine the string representation BEFORE building metadata
                if category == "Formula":
                    page_content = text_as_html or getattr(element_meta, "formula", None) or raw_text or "[Formula]"
                elif category == "Table":
                    # Jina AI performs best with HTML table structures
                    page_content = text_as_html or raw_text or "[Table]"
                elif category == "Image":
                    # If no OCR text, provide a descriptor for the CLIP embedder
                    page_content = raw_text or f"Visual element: {category}"
                else:
                    # Fallback chain to avoid NoneType __str__ crash
                    page_content = raw_text or (str(element) if element is not None else None) or f"[{category}]"

                # 3. Skip "Ghost" Elements (No text, no HTML, no Image data)
                # This prevents polluting your Vector DB with empty entries
                has_image = hasattr(element_meta, "image_base64")
                if not page_content.strip() and not has_image:
                    continue

                # 4. Build enhanced metadata
                metadata = blob.metadata.copy() if blob.metadata else {}
                metadata.update({
                    "element_type": category,
                    "has_formula": category == "Formula",
                })

                # Capture specific rich data in metadata
                if category == "Formula":
                    metadata["formula_latex"] = page_content
                elif category == "Table" and text_as_html:
                    metadata["table_html"] = text_as_html
                elif category == "Image":
                    if has_image:
                        metadata["image_data"] = element_meta.image_base64
                    if hasattr(element_meta, "image_path"):
                        metadata["image_path"] = element_meta.image_path

                # Preserve coordinates (SERIALIZED)
                coords = getattr(element_meta, "coordinates", None)
                if coords:
                    # Convert the complex Coordinate object into a dict if possible
                    coord_data = coords.to_dict() if hasattr(coords, "to_dict") else coords
                    metadata["coordinates"] = self._serialize_metadata_value(coord_data)

                # Preserve page number
                page_num = getattr(element_meta, "page_number", None)
                if page_num is not None:
                    metadata["page_number"] = int(page_num)

                # Final serialization for DB compatibility
                metadata = self._serialize_metadata_value(metadata)

                yield Document(
                    page_content=str(page_content),
                    metadata=metadata
                )
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    @property
    def document_loader_type(self) -> Type[UnstructuredFileLoader]:
        return self._document_loader_type
