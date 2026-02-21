import asyncio
import hashlib
import json
import mimetypes
import os
import re
import time
import uuid
from io import BytesIO
from typing import List, Dict, Tuple
from httpx import AsyncClient
from langchain_community.document_loaders.parsers.generic import MimeTypeBasedParser
from langchain_core.documents.base import Document, Blob

from cat.log import log
from cat.services.factory.chunker import BaseChunker
from cat.services.memory.models import VectorMemoryType, PointStruct
from cat.utils import is_url as fnc_is_url


class RabbitHole:
    def __init__(self):
        self.cat = None
        self.stray = None
        self.embedder = None

    def setup(self, _cat: "BotMixin"):
        from cat.looking_glass import CheshireCat, StrayCat

        if isinstance(_cat, CheshireCat):
            self.cat = _cat
            self.stray = None
            return

        if isinstance(_cat, StrayCat):
            self.stray = _cat
            self.cat = _cat.lizard.get_cheshire_cat(_cat.agent_key)
            return

        raise ValueError("RabbitHole can only be setup with CheshireCat or StrayCat instances.")

    """Manages content ingestion. I'm late... I'm late!"""

    async def ingest_memory(self, cat: "CheshireCat", file: BytesIO, filename: str):
        """Upload memories to the declarative memory from a JSON file.

        Args:
            cat (CheshireCat): Cheshire Cat instance.
            file (BytesIO): JSON file containing vector and content memories.
            filename (str): Filename of the uploaded file.

        Notes
        -----
        This method allows uploading a JSON file containing vector and content memories directly to the declarative
        memory.
        When doing this, please, make sure the embedder used to export the memories is the same as the one used
        when uploading.
        The method also performs a check on the dimensionality of the embeddings (i.e. length of each vector).
        """
        try:
            self.setup(cat)
            lizard = self.cat.lizard

            # Load fyle byte in a dict
            memories = json.loads(file.read().decode("utf-8"))

            # Check the embedder used for the uploaded memories is the same the Cat is using now
            upload_embedder = memories["embedder"]
            cat_embedder = str(lizard.embedder.__class__.__name__)
            if upload_embedder != cat_embedder:
                raise Exception(f"Embedder mismatch for file '{filename}': file embedder {upload_embedder} is different from {cat_embedder}")

            # Get Declarative memories in file
            declarative_memories = memories["collections"][str(VectorMemoryType.DECLARATIVE)]
            if not declarative_memories:
                raise Exception(f"No Declarative memories found in the uploaded file '{filename}'.")

            # Store data to upload the memories in batch
            points = [PointStruct(
                id=m["id"],
                payload={"page_content": m["page_content"], "metadata": m["metadata"]},
                vector=m["vector"],
            ) for m in declarative_memories]

            log.info(f"Agent id: {self.cat.agent_key}. Preparing to load {len(points)} vector memories")

            # Check embedding size is correct
            embedder_size = lizard.embedder_size
            len_mismatch = [len(p.vector) == embedder_size for p in points]

            if not any(len_mismatch):
                raise Exception(f"Embedding size mismatch for file '{filename}': vectors length should be {embedder_size}")

            # Upsert memories in batch mode
            await cat.vector_memory_handler.add_points_to_tenant(
                collection_name=str(VectorMemoryType.DECLARATIVE), points=points,
            )
        except Exception as e:
            log.error(f"Error uploading memories from file '{filename}': {e}")

    async def ingest_file(
        self,
        cat: "BotMixin",
        file: str | BytesIO,
        metadata: Dict,
        filename: str | None = None,
        store_file: bool = True,
        content_type: str | None = None,
    ):
        """
        Load a file in the Cat's declarative memory.

        The method splits and converts the file in Langchain `Document`. Then, it stores the `Document` in the Cat's
        memory.

        Args:
            cat (CheshireCat | StrayCat): Cheshire Cat or Stray Cat instance.
            file (str | BytesIO): The file can be a path passed as a string or a `BytesIO` object if the document is ingested using the `rabbithole` endpoint.
            metadata (Dict): Metadata to be stored with each chunk.
            filename (str): The filename of the file to be ingested, if coming from the `/rabbithole/` endpoint.
            store_file (bool): Whether to store the file in the Cat's file storage.
            content_type (str): The content type of the file. If not provided, it will be guessed based on the file extension.

        See Also:
            before_rabbithole_stores_documents
        """
        source = ""
        points = []

        try:
            self.setup(cat)

            filename = filename or (file if isinstance(file, str) else None)
            if not filename:
                raise ValueError("No filename provided.")

            # split a file into a list of docs
            source, file_bytes, content_type, docs, is_url = await self._file_to_docs(
                file=file, filename=filename, content_type=content_type
            )
            if not docs:
                raise Exception(f"No valid chunks found in the file '{filename}'.")

            # store in memory
            sha256 = hashlib.sha256()
            sha256.update(file_bytes)
            points = await self._store_documents(
                docs=docs, source=source, file_hash=sha256.hexdigest(), metadata=metadata,
            )

            # store in file storage
            if store_file and not is_url:
                chat_id = self.stray.id if self.stray else None
                self.cat.save_file(file_bytes, content_type, source, chat_id)

            # notify client
            await self._send_ws_message(f"Finished reading {source}, I made {len(docs)} thoughts on it.")

            log.info(f"Agent id: {self.cat.agent_key}. Successfully ingested file: {filename}")
        except Exception as e:
            log.error(f"Error ingesting file {filename}: {e}")
            # Don't raise in background tasks - just log the error
            if self.stray:
                try:
                    await self.stray.notifier.send_error(f"Error processing {filename}: {str(e)}")
                except Exception as notify_error:
                    log.error(f"Failed to send error notification: {notify_error}")
        finally:
            # hook the points after they are stored in the vector memory
            self.cat.plugin_manager.execute_hook(
                "after_rabbithole_stored_documents", source, points, caller=self.stray or self.cat,
            )

    async def _file_to_docs(
        self, file: str | BytesIO, filename: str, content_type: str | None = None
    ) -> Tuple[str, bytes, str | None, List[Document], bool]:
        """
        Load and convert files to Langchain `Document`.

        This method takes a file either from a Python script, from the `/rabbithole/` or `/rabbithole/web` endpoints.
        Hence, it loads it in memory and splits it in chunks.

        Args:
            file (str | BytesIO): The file can be either a string path if loaded programmatically, a `BytesIO` if coming from the `/rabbithole/` endpoint, or a URL if coming from the `/rabbithole/web` endpoint.
            filename (str): The filename of the file to be ingested.
            content_type (str): The content type of the file. If not provided, it will be guessed based on the file extension.

        Returns:
            (source, file_bytes, content_type, docs, is_url): Tuple[str, bytes, str | None, List[Document], bool].
                The file name, the file content in bytes, the content type, the list of chunked Langchain `Document` and
                a boolean indicating if the file was loaded from a URL.
        """
        def sanitize_filename(file_name: str) -> str:
            if "." not in file_name:
                return file_name
            # Split on the LAST dot only (if any)
            base, ext = file_name.rsplit(".", 1)
            ext = "." + ext
            # Replace any sequence of dots or spaces in the base name only
            base = re.sub(r"[.\s]+", "_", base)
            return base + ext

        async def parse() -> Tuple[str | None, bytes | None, str | None, bool]:
            if isinstance(file, BytesIO):
                # Get the source of UploadFile, file bytes and whether it's a URL
                return sanitize_filename(filename), file.read(), content_type, False
            if fnc_is_url(file):
                try:
                    # Make a request with a fake browser name - use async httpx
                    async with AsyncClient() as client:
                        response = await client.get(file, headers={"User-Agent": "Magic Browser"})
                        response.raise_for_status()
                        # Define mime type and source of url
                        # Add fallback for empty/None content_type
                        ct = response.headers.get(
                            "Content-Type", "text/html" if file.startswith("http") else "text/plain"
                        ).split(";")[0]
                        # Get binary content of url
                        return file, response.content, ct, True
                except Exception as e:
                    log.error(f"Agent id: {self.cat.agent_key}. Error: {e}")
                    return None, None, content_type, True
            # Get file bytes - use async file reading
            fb = await asyncio.to_thread(lambda: open(file, "rb").read())
            return sanitize_filename(os.path.basename(file)), fb, mimetypes.guess_type(file)[0], False

        if not isinstance(file, BytesIO) and not isinstance(file, str):
            raise ValueError(f"{type(file)} is not a valid type.")

        # Check the characteristics of the incoming file.
        source, file_bytes, content_type, is_url = await parse()
        if not file_bytes:
            raise ValueError(f"Something went wrong with the source '{source}'")

        log.debug(f"Attempting to parse source: {source}. Detected MIME type: {content_type}. Available handlers: {list(self.cat.file_handlers.keys())}")

        # Load the bytes in the Blob schema and parse the content. Parser based on the mime type
        await self._send_ws_message("I'm parsing the content. Big content could require some minutes...")
        super_docs = MimeTypeBasedParser(handlers=self.cat.file_handlers).parse(
            Blob(data=file_bytes, mimetype=content_type).from_data(data=file_bytes, mime_type=content_type, path=source)
        )

        # Split
        await self._send_ws_message("Parsing completed. Now let's go with reading process...")
        docs = self._split_text(docs=super_docs)
        return source, file_bytes, content_type, docs, is_url

    async def _store_documents(
        self,
        docs: List[Document],
        source: str,
        file_hash: str,
        metadata: Dict,
    ) -> List[PointStruct]:
        """Add documents to the Cat's declarative memory.

        This method loops a list of Langchain `Document` and adds some metadata. Namely, the source filename and the
        timestamp of insertion. Once done, the method notifies the client via Websocket connection.

        Args:
            docs (List[Document]): List of Langchain `Document` to be inserted in the Cat's declarative memory.
            source (str): Source name to be added as a metadata. It can be a file name or an URL.
            file_hash (str): Hash of the file to be added as a metadata.
            metadata (Dict): Metadata to be stored with each chunk.

        Returns:
            stored_points (List[PointStruct]): List of points stored in the Cat's declarative memory.

        See Also:
            before_rabbithole_stores_documents
            after_rabbithole_stored_documents

        Notes
        -------
        At this point, it is possible to customize the Cat's behavior using the `before_rabbithole_stores_documents`
        hook to edit the memories before they are inserted in the vector database.
        The hook `after_rabbithole_stored_documents` could be used to track the end of the process, indeed.
        """
        log.info(f"Agent id: {self.cat.agent_key}. Preparing to memorize {len(docs)} vectors for {source}.")

        embedder = self.cat.lizard.embedder
        plugin_manager = self.cat.plugin_manager

        # add custom metadata (sent via endpoint) and default metadata (source and when and eventual chat_id)
        for doc in docs:
            doc.metadata = (
                    doc.metadata
                    | metadata
                    | {"source": source, "when": time.time(), "hash": file_hash}
                    | ({"chat_id": self.stray.id} if self.stray else {})
            )

        # hook the docs before they are stored in the vector memory
        docs = plugin_manager.execute_hook("before_rabbithole_stores_documents", docs, caller=self.stray or self.cat)

        # hook the points before they are stored in the vector memory
        valid_documents = list(filter(lambda doc_: doc_.page_content.strip(), docs))
        storing_vectors = await asyncio.to_thread(
            lambda: embedder.embed_documents([doc_.page_content for doc_ in valid_documents])
        )
        points = [PointStruct(
            id=uuid.uuid4().hex,
            payload=doc.model_dump(),
            vector=vector,
        ) for doc, vector in zip(valid_documents, storing_vectors)]

        collection_name = str(VectorMemoryType.DECLARATIVE if not self.stray else VectorMemoryType.EPISODIC)
        await self.cat.vector_memory_handler.add_points_to_tenant(collection_name=collection_name, points=points)

        return points

    def _split_text(self, docs: List[Document]):
        """Split LangChain documents in chunks.

        This method splits the incoming documents in chunks. Other two hooks are available to edit the
        documents before and after the split step.

        Args:
            docs (List[Document]): Content of the loaded file.

        Returns:
            docs (List[Document]): List of split Langchain `Document`.

        See Also:
            before_rabbithole_splits_documents

        Notes
        -----
        The default behavior splits the content and executes the hooks, before the splitting.
        `before_rabbithole_splits_documents` hook returns the original input without any modification.
        """
        plugin_manager = self.cat.plugin_manager

        # do something on the docs before they are split
        docs = plugin_manager.execute_hook("before_rabbithole_splits_documents", docs, caller=self.stray or self.cat)

        # split docs
        chunker = self.cat.chunker
        docs = chunker.split_documents(docs)

        # join each short chunk with previous one, instead of deleting them
        try:
            return self._merge_short_chunks(docs, chunker)
        except Exception as e:
            # Log error but don't fail the entire process
            log.warning(f"Error merging short chunks: {e}. Proceeding with original chunks.")
            return docs

    def _merge_short_chunks(self, docs: List[Document], chunker: BaseChunker) -> List[Document]:
        """Safely merge short chunks with adjacent ones.

        Args:
            docs: List of documents to process
            chunker: The chunker instance for configuration

        Returns:
            List of documents with short chunks merged
        """
        def should_merge_chunk() -> bool:
            """Determine if a chunk should be merged."""
            return (
                    min_chunk_size > len(current_content) > 0 and  # Don't merge empty content
                    len(merged_docs) > 0  # Need previous chunk to merge with
            )

        def can_safely_merge(prev_doc: Document) -> bool:
            """Check if two documents can be safely merged."""
            potential_size = len(prev_doc.page_content) + len(current_doc.page_content) + 2
            return potential_size <= max_merge_size

        if not docs:
            return docs

        # Get configuration with safe defaults
        chunk_size = getattr(chunker.analyzer, "chunk_size", getattr(chunker.analyzer, "max_chunk_size", 1000))
        chunk_overlap = getattr(chunker.analyzer, "chunk_overlap", 100)

        # Conservative thresholds
        min_chunk_size = max(50, chunk_size // 20)  # At least 50 chars
        max_merge_size = chunk_size + chunk_overlap  # Respect splitter's intended size

        merged_docs = []
        i = 0

        while i < len(docs):
            current_doc = docs[i]
            current_content = current_doc.page_content.strip()

            # Check if this chunk should be merged
            if should_merge_chunk() and can_safely_merge(merged_docs[-1]):
                try:
                    merged_docs[-1] = self._create_merged_document(merged_docs[-1], current_doc)
                except Exception:
                    # If merge fails, keep both documents separate
                    merged_docs.append(current_doc)
            else:
                merged_docs.append(current_doc)

            i += 1

        return merged_docs

    def _create_merged_document(self, prev_doc: Document, current_doc: Document) -> Document:
        """Create a new merged document safely."""
        # Merge content with clear separator
        merged_content = prev_doc.page_content.rstrip() + "\n\n" + current_doc.page_content.lstrip()

        # Merge metadata - since source is the same, we can safely combine
        merged_metadata = prev_doc.metadata.copy()

        # Add all metadata from current doc, handling conflicts intelligently
        for key, value in current_doc.metadata.items():
            if key in merged_metadata and merged_metadata[key] != value:
                # For numeric values (like page numbers), take the range or sum
                if isinstance(merged_metadata[key], (int, float)) and isinstance(value, (int, float)):
                    if key in ["page", "page_number", "chunk_index"]:
                        # For page/chunk numbers, keep the starting one
                        pass  # Keep the previous value
                    else:
                        # For other numeric values, might want to sum or take max
                        merged_metadata[key] = max(merged_metadata[key], value)
                else:
                    # For other conflicts, keep the first value
                    pass
            else:
                merged_metadata[key] = value

        # Add merge tracking
        merge_count = merged_metadata.get("_merge_count", 1) + 1
        merged_metadata["_merge_count"] = merge_count
        merged_metadata["_is_merged"] = True

        return Document(page_content=merged_content, metadata=merged_metadata)

    async def _send_ws_message(self, message: str):
        if self.stray and self.stray.notifier.has_ws_connection():
            await self.stray.notifier.send_ws_message(message)
