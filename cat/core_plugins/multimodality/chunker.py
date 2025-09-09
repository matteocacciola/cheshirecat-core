from typing import Type
from pydantic import ConfigDict

from cat.factory.chunker import BaseChunker, ChunkerSettings
from typing import Iterable, List
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter
import base64
from PIL import Image
import io
import hashlib


class ImageChunker(BaseChunker):
    def __init__(self, max_chunk_size: int, min_chunk_size: int | None = None):
        self._max_chunk_size = max_chunk_size
        self._min_chunk_size = min_chunk_size or max_chunk_size // 4
        self._tile_overlap = 50  # Overlap in pixels for image tiles

    @property
    def analyzer(self):
        """Returns a RecursiveCharacterTextSplitter for text content associated with images"""
        return RecursiveCharacterTextSplitter(
            chunk_size=self._max_chunk_size,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    # def _create_image_tiles(self, image_data: bytes, image_format: str) -> List[bytes]:
    #     """Create overlapping tiles from an image"""
    #     try:
    #         image = Image.open(io.BytesIO(image_data))
    #         width, height = image.size
    #
    #         # Calculate tile dimensions based on max_chunk_size
    #         # Assuming max_chunk_size relates to approximate file size in KB
    #         target_pixels = self._max_chunk_size * 1024 // 3  # Rough estimate for RGB
    #         tile_size = int(target_pixels ** 0.5)
    #         tile_size = min(tile_size, min(width, height))
    #         tile_size = max(tile_size, 256)  # Minimum tile size
    #
    #         tiles = []
    #         overlap = self._tile_overlap
    #
    #         for y in range(0, height - tile_size + 1, tile_size - overlap):
    #             for x in range(0, width - tile_size + 1, tile_size - overlap):
    #                 # Ensure we don't exceed image boundaries
    #                 x_end = min(x + tile_size, width)
    #                 y_end = min(y + tile_size, height)
    #
    #                 tile = image.crop((x, y, x_end, y_end))
    #
    #                 # Convert tile to bytes
    #                 buffer = io.BytesIO()
    #                 tile.save(buffer, format=image_format.upper())
    #                 tile_bytes = buffer.getvalue()
    #
    #                 # Only include tiles that meet minimum size requirements
    #                 if len(tile_bytes) >= self._min_chunk_size:
    #                     tiles.append(tile_bytes)
    #
    #         return tiles if tiles else [image_data]  # Return original if no valid tiles
    #     except Exception:
    #         # If tiling fails, return original image
    #         return [image_data]
    #
    # def _get_image_metadata(self, image_data: bytes) -> dict:
    #     """Extract metadata from image"""
    #     try:
    #         image = Image.open(io.BytesIO(image_data))
    #         return {
    #             "width": image.size[0],
    #             "height": image.size[1],
    #             "format": image.format,
    #             "mode": image.mode,
    #             "size_bytes": len(image_data)
    #         }
    #     except Exception:
    #         return {"size_bytes": len(image_data)}

    # def split_documents(self, documents: Iterable[Document]) -> List[Document]:
    #     """Split documents containing images into manageable chunks"""
    #     chunked_documents = []
    #
    #     for doc in documents:
    #         # Check if document contains image data
    #         if self._is_image_document(doc):
    #             chunks = self._split_image_document(doc)
    #             chunked_documents.extend(chunks)
    #         else:
    #             # Handle text documents with potential image references
    #             text_chunks = self.analyzer.split_documents([doc])
    #             chunked_documents.extend(text_chunks)
    #
    #     return chunked_documents
    #
    # def _is_image_document(self, doc: Document) -> bool:
    #     """Check if document contains image data"""
    #     return (
    #             "image_data" in doc.metadata or
    #             "image_base64" in doc.metadata or
    #             (doc.page_content.startswith("data:image/") or
    #              any(doc.page_content.lower().endswith(ext) for ext in
    #                  ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']))
    #     )
    #
    # def _split_image_document(self, doc: Document) -> List[Document]:
    #     """Split a document containing image data"""
    #     chunks = []
    #
    #     # Extract image data
    #     image_data = None
    #     image_format = "PNG"
    #
    #     if "image_data" in doc.metadata:
    #         image_data = doc.metadata["image_data"]
    #         image_format = doc.metadata.get("image_format", "PNG")
    #     elif "image_base64" in doc.metadata:
    #         image_data = base64.b64decode(doc.metadata["image_base64"])
    #         image_format = doc.metadata.get("image_format", "PNG")
    #     elif doc.page_content.startswith("data:image/"):
    #         # Handle base64 data URLs
    #         header, data = doc.page_content.split(",", 1)
    #         image_format = header.split("/")[1].split(";")[0].upper()
    #         image_data = base64.b64decode(data)
    #
    #     if image_data and len(image_data) > self._max_chunk_size:
    #         # Create image tiles
    #         tiles = self._create_image_tiles(image_data, image_format)
    #
    #         for i, tile_data in enumerate(tiles):
    #             tile_metadata = doc.metadata.copy()
    #             tile_metadata.update({
    #                 "chunk_id": f"{doc.metadata.get('source', 'unknown')}_{i}",
    #                 "chunk_index": i,
    #                 "total_chunks": len(tiles),
    #                 "is_image_chunk": True,
    #                 "original_image_hash": hashlib.md5(image_data).hexdigest()[:8],
    #                 **self._get_image_metadata(tile_data)
    #             })
    #
    #             # Store tile as base64 in page_content for vector storage
    #             tile_b64 = base64.b64encode(tile_data).decode('utf-8')
    #
    #             chunk_doc = Document(
    #                 page_content=f"data:image/{image_format.lower()};base64,{tile_b64}",
    #                 metadata=tile_metadata
    #             )
    #             chunks.append(chunk_doc)
    #     else:
    #         # Image is small enough, keep as single chunk
    #         chunk_metadata = doc.metadata.copy()
    #         chunk_metadata.update({
    #             "is_image_chunk": True,
    #             "chunk_index": 0,
    #             "total_chunks": 1,
    #             **(self._get_image_metadata(image_data) if image_data else {})
    #         })
    #
    #         chunks.append(Document(
    #             page_content=doc.page_content,
    #             metadata=chunk_metadata
    #         ))
    #
    #     return chunks


class ImageChunkerSettings(ChunkerSettings):
    max_chunk_size: int = 2000
    min_chunk_size: int | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Image Semantic chunker",
            "description": "Configuration for Image semantic chunker to be used to chunk images into smaller parts",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return ImageChunker
