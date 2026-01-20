import asyncio
import json
import mimetypes
import os
import re
import time
from io import BytesIO
from typing import List, Dict, Tuple
from urllib.error import HTTPError
import httpx
from langchain_community.document_loaders.parsers.generic import MimeTypeBasedParser
from langchain_core.documents.base import Document, Blob

from cat.log import log
from cat.services.factory.chunker import BaseChunker
from cat.services.memory.models import PointStruct, VectorMemoryType
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

    async def ingest_memory(self, cat: "CheshireCat", file: BytesIO):
        """Upload memories to the declarative memory from a JSON file.

        Args:
            cat (CheshireCat): Cheshire Cat instance.
            file (BytesIO): JSON file containing vector and content memories.

        Notes
        -----
        This method allows uploading a JSON file containing vector and content memories directly to the declarative
        memory.
        When doing this, please, make sure the embedder used to export the memories is the same as the one used
        when uploading.
        The method also performs a check on the dimensionality of the embeddings (i.e. length of each vector).
        """
        self.setup(cat)
        lizard = self.cat.lizard

        # Get file bytes
        file_bytes = file.read()

        # Load fyle byte in a dict
        memories = json.loads(file_bytes.decode("utf-8"))

        # Check the embedder used for the uploaded memories is the same the Cat is using now
        upload_embedder = memories["embedder"]
        cat_embedder = str(lizard.embedder.__class__.__name__)

        if upload_embedder != cat_embedder:
            raise Exception(
                f"Embedder mismatch: file embedder {upload_embedder} is different from {cat_embedder}"
            )

        # Get Declarative memories in file
        declarative_memories = memories["collections"][str(VectorMemoryType.DECLARATIVE)]

        # Store data to upload the memories in batch
        ids = [m["id"] for m in declarative_memories]
        payloads = [
            {"page_content": m["page_content"], "metadata": m["metadata"]}
            for m in declarative_memories
        ]
        vectors = [m["vector"] for m in declarative_memories]

        log.info(f"Agent id: {self.cat.agent_key}. Preparing to load {len(vectors)} vector memories")

        # Check embedding size is correct
        embedder_size = lizard.embedder_size
        len_mismatch = [len(v) == embedder_size for v in vectors]

        if not any(len_mismatch):
            raise Exception(
                f"Embedding size mismatch: vectors length should be {embedder_size}"
            )

        # Upsert memories in batch mode
        await cat.vector_memory_handler.add_points_to_tenant(
            collection_name=str(VectorMemoryType.DECLARATIVE), ids=ids, payloads=payloads, vectors=vectors
        )

    async def ingest_file(
        self,
        cat: "BotMixin",
        file: str | BytesIO,
        filename: str | None = None,
        metadata: Dict = None,
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
            filename (str): The filename of the file to be ingested, if coming from the `/rabbithole/` endpoint.
            metadata (Dict): Metadata to be stored with each chunk.
            store_file (bool): Whether to store the file in the Cat's file storage.
            content_type (str): The content type of the file. If not provided, it will be guessed based on the file extension.

        See Also:
            before_rabbithole_stores_documents
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

        try:
            self.setup(cat)

            filename = filename or (file if isinstance(file, str) else None)
            if not filename:
                raise ValueError("No filename provided.")

            # replace multiple spaces with underscore
            filename = sanitize_filename(filename)

            # split a file into a list of docs
            file_bytes, content_type, docs, is_url = await self._file_to_docs(
                file=file, filename=filename, content_type=content_type
            )

            # store in memory
            await self._store_documents(docs=docs, source=filename, metadata=metadata)

            # store in file storage
            if store_file and not is_url:
                chat_id = self.stray.id if self.stray else None
                self.cat.save_file(file_bytes, content_type, filename, chat_id)

            log.info(f"Successfully ingested file: {filename}")
        except Exception as e:
            log.error(f"Error ingesting file {filename}: {e}")
            # Don't raise in background tasks - just log the error
            if self.stray:
                try:
                    await self.stray.notifier.send_error(
                        f"Error processing {filename}: {str(e)}"
                    )
                except Exception as notify_error:
                    log.error(f"Failed to send error notification: {notify_error}")

    async def _file_to_docs(
        self, file: str | BytesIO, filename: str, content_type: str | None = None
    ) -> Tuple[bytes, str | None, List[Document], bool]:
        """
        Load and convert files to Langchain `Document`.

        This method takes a file either from a Python script, from the `/rabbithole/` or `/rabbithole/web` endpoints.
        Hence, it loads it in memory and splits it in chunks.

        Args:
            file (str | BytesIO): The file can be either a string path if loaded programmatically, a `BytesIO` if coming from the `/rabbithole/` endpoint, or a URL if coming from the `/rabbithole/web` endpoint.
            filename (str): The filename of the file to be ingested.
            content_type (str): The content type of the file. If not provided, it will be guessed based on the file extension.

        Returns:
            (bytes, content_type, docs, is_url): Tuple[bytes, str | None, List[Document], bool]. The file bytes, the
                content type, the list of chunked Langchain `Document` and a boolean indicating if the file was loaded
                from a URL.
        """
        source = None
        file_bytes = None

        if not isinstance(file, BytesIO) and not isinstance(file, str):
            raise ValueError(f"{type(file)} is not a valid type.")

        # Check type of incoming file.
        is_url = False
        if isinstance(file, BytesIO):
            # Get mime type and source of UploadFile
            source = filename

            # Get file bytes
            file_bytes = file.read()
        else:
            is_url = fnc_is_url(file)
            if is_url:
                try:
                    # Make a request with a fake browser name - use async httpx
                    async with httpx.AsyncClient() as client:
                        response = await client.get(file, headers={"User-Agent": "Magic Browser"})
                        response.raise_for_status()

                        # Define mime type and source of url
                        # Add fallback for empty/None content_type
                        content_type = response.headers.get(
                            "Content-Type", "text/html" if file.startswith("http") else "text/plain"
                        ).split(";")[0]
                        source = file

                        # Get binary content of url
                        file_bytes = response.content
                except HTTPError as e:
                    log.error(f"Agent id: {self.cat.agent_key}. Error: {e}")
            else:
                # Get mime type from file extension and source
                content_type = mimetypes.guess_type(file)[0]
                source = os.path.basename(file)

                # Get file bytes - use async file reading
                file_bytes = await asyncio.to_thread(lambda: open(file, "rb").read())

        if not file_bytes:
            raise ValueError(f"Something went wrong with the file {source}")

        log.debug(f"Attempting to parse file: {source}")
        log.debug(f"Detected MIME type: {content_type}")
        log.debug(f"Available handlers: {list(self.cat.file_handlers.keys())}")

        # Load the bytes in the Blob schema
        blob = Blob(data=file_bytes, mimetype=content_type).from_data(
            data=file_bytes, mime_type=content_type, path=source
        )
        # Parser based on the mime type
        parser = MimeTypeBasedParser(handlers=self.cat.file_handlers)

        # Parse the content
        await self._send_ws_message(
            "I'm parsing the content. Big content could require some minutes..."
        )
        super_docs = parser.parse(blob)

        # Split
        await self._send_ws_message("Parsing completed. Now let's go with reading process...")
        docs = self._split_text(docs=super_docs)
        return file_bytes, content_type, docs, is_url

    async def _store_documents(
        self,
        docs: List[Document],
        source: str,
        metadata: Dict = None
    ) -> List[PointStruct]:
        """Add documents to the Cat's declarative memory.

        This method loops a list of Langchain `Document` and adds some metadata. Namely, the source filename and the
        timestamp of insertion. Once done, the method notifies the client via Websocket connection.

        Args:
            docs (List[Document]): List of Langchain `Document` to be inserted in the Cat's declarative memory.
            source (str): Source name to be added as a metadata. It can be a file name or an URL.
            metadata (Dict): Metadata to be stored with each chunk.

        Returns:
            stored_points (List[PointStruct]): List of points stored in the Cat's declarative memory.

        See Also:
            before_rabbithole_insert_memory

        Notes
        -------
        At this point, it is possible to customize the Cat's behavior using the `before_rabbithole_insert_memory` hook
        to edit the memories before they are inserted in the vector database.
        """
        log.info(f"Agent id: {self.cat.agent_key}. Preparing to memorize {len(docs)} vectors for {source}.")

        embedder = self.cat.lizard.embedder
        plugin_manager = self.cat.plugin_manager

        # hook the docs before they are stored in the vector memory
        docs = plugin_manager.execute_hook("before_rabbithole_stores_documents", docs, caller=self.stray or self.cat)

        # classic embed
        time_last_notification = time.time()
        time_interval = 10  # a notification every 10 secs

        storing_points = []
        storing_payloads = []
        storing_vectors = []
        for d, doc in enumerate(docs):
            if time.time() - time_last_notification > time_interval:
                time_last_notification = time.time()
                perc_read = int(d / len(docs) * 100)
                read_message = f"Read {perc_read}% of {source}"
                await self._send_ws_message(read_message)

                log.info(read_message)

            # add custom metadata (sent via endpoint) and default metadata (source and when)
            doc.metadata = (metadata or {}) | doc.metadata | {"source": source, "when": time.time()}
            if self.stray:
                doc.metadata["chat_id"] = self.stray.id

            doc = plugin_manager.execute_hook("before_rabbithole_insert_memory", doc, caller=self.stray or self.cat)
            if doc.page_content != "":
                payload = doc.model_dump()
                vector = await asyncio.to_thread(lambda: embedder.embed_documents([doc.page_content])[0])

                storing_points.append(PointStruct(id=None, payload=payload, vector=vector))
                storing_payloads.append(payload)
                storing_vectors.append(vector)

            # wait a little to avoid APIs rate limit errors
            await asyncio.sleep(0.05)

        collection_name = str(VectorMemoryType.DECLARATIVE if not self.stray else VectorMemoryType.EPISODIC)
        await self.cat.vector_memory_handler.add_points_to_tenant(
            collection_name=collection_name, payloads=storing_payloads, vectors=storing_vectors,
        )

        # hook the points after they are stored in the vector memory
        plugin_manager.execute_hook(
            "after_rabbithole_stored_documents", source, storing_points, caller=self.stray or self.cat
        )

        # notify client
        await self._send_ws_message(f"Finished reading {source}, I made {len(docs)} thoughts on it.")

        log.info(
            f"Agent id: {self.cat.agent_key}. Done uploading {source}. Inserted #{len(storing_points)} points into {collection_name} memory."
        )

        return storing_points

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
