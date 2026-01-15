import json
import mimetypes
import os
import tempfile
import time
from io import BytesIO
from typing import List, Dict, Tuple
from urllib.error import HTTPError
from urllib.parse import urlparse
import httpx
from langchain_community.document_loaders.parsers.generic import MimeTypeBasedParser
from langchain_core.documents.base import Document, Blob

from cat.log import log
from cat.services.factory.chunker import BaseChunker
from cat.services.memory.models import PointStruct, VectorMemoryType


class RabbitHole:
    def __init__(self):
        self.cat = None
        self.stray = None
        self.embedder = None

    def setup(self, _cat: "BotMixin"):
        from cat.looking_glass import CheshireCat, StrayCat

        if isinstance(_cat, CheshireCat):
            self.cat = _cat
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

        log.info(f"Agent id: {self.cat.id}. Preparing to load {len(vectors)} vector memories")

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

        See Also:
            before_rabbithole_stores_documents

        Notes
        ----------
        Currently supported formats are `.txt`, `.pdf` and `.md`.
        You can add custom ones or substitute the above via RabbitHole hooks.
        """
        self.setup(cat)

        filename = filename or (file if isinstance(file, str) else None)
        if not filename:
            raise ValueError("No filename provided.")

        # split a file into a list of docs
        file_bytes, content_type, docs = await self._file_to_docs(file=file, filename=filename)

        # store in memory
        await self._store_documents(docs=docs, source=filename, metadata=metadata)

        # store in file storage
        if store_file:
            await self._save_file(file_bytes, content_type, filename)

    async def _file_to_docs(self, file: str | BytesIO, filename: str) -> Tuple[bytes, str | None, List[Document]]:
        """
        Load and convert files to Langchain `Document`.

        This method takes a file either from a Python script, from the `/rabbithole/` or `/rabbithole/web` endpoints.
        Hence, it loads it in memory and splits it in chunks.

        Args:
            file (str | BytesIO): The file can be either a string path if loaded programmatically, a `BytesIO` if coming from the `/rabbithole/` endpoint, or a URL if coming from the `/rabbithole/web` endpoint.
            filename (str): The filename of the file to be ingested.

        Returns:
            (bytes, content_type, docs): Tuple[bytes, List[Document]]. The file bytes, the content type and the list of chunked Langchain `Document`.

        Notes
        -----
        This method is used by both `/rabbithole/` and `/rabbithole/web` endpoints.
        Currently supported files are `.txt`, `.pdf`, `.md` and web pages.
        """
        source = None
        content_type = None
        file_bytes = None

        # Check type of incoming file.
        if isinstance(file, BytesIO):
            # Get mime type and source of UploadFile
            content_type = mimetypes.guess_type(filename)[0]
            source = filename

            # Get file bytes
            file_bytes = file.read()
        elif isinstance(file, str):
            # Check if a string file is a string or url
            parsed_file = urlparse(file)
            is_url = all([parsed_file.scheme, parsed_file.netloc])

            if is_url:
                try:
                    # Make a request with a fake browser name
                    response = httpx.get(file, headers={"User-Agent": "Magic Browser"})
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

                # Get file bytes
                with open(file, "rb") as f:
                    file_bytes = f.read()
        else:
            raise ValueError(f"{type(file)} is not a valid type.")

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
        if self.stray:
            await self.stray.notifier.send_ws_message(
                "I'm parsing the content. Big content could require some minutes..."
            )
        super_docs = parser.parse(blob)

        # Split
        if self.stray:
            await self.stray.notifier.send_ws_message("Parsing completed. Now let's go with reading process...")
        docs = self._split_text(docs=super_docs)
        return file_bytes, content_type, docs

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
                if self.stray:
                    await self.stray.notifier.send_ws_message(read_message)

                log.info(read_message)

            # add custom metadata (sent via endpoint) and default metadata (source and when)
            doc.metadata = (metadata or {}) | doc.metadata | {"source": source, "when": time.time()}

            doc = plugin_manager.execute_hook("before_rabbithole_insert_memory", doc, caller=self.stray or self.cat)
            if doc.page_content != "":
                payload = doc.model_dump()
                vector = embedder.embed_documents([doc.page_content])[0]

                storing_points.append(PointStruct(id=None, payload=payload, vector=vector))
                storing_payloads.append(payload)
                storing_vectors.append(vector)

            # wait a little to avoid APIs rate limit errors
            time.sleep(0.05)

        await self.cat.vector_memory_handler.add_points_to_tenant(
            collection_name=str(VectorMemoryType.DECLARATIVE), payloads=storing_payloads, vectors=storing_vectors,
        )

        # hook the points after they are stored in the vector memory
        plugin_manager.execute_hook(
            "after_rabbithole_stored_documents", source, storing_points, caller=self.stray or self.cat
        )

        # notify client
        if self.stray:
            await self.stray.notifier.send_ws_message(f"Finished reading {source}, I made {len(docs)} thoughts on it.")

        log.info(
            f"Agent id: {self.cat.agent_key}. Done uploading {source}. Inserted #{len(storing_points)} points into memory."
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

    async def _save_file(self, file_bytes: bytes, content_type: str, source: str):
        """
        Save file in the Rabbit Hole remote storage handled by the CheshireCat's file manager.
        This method saves the file in the Rabbit Hole storage. The file is saved in a temporary folder and the path is
        stored in the remote storage handled by the CheshireCat's file manager.

        Args:
            file_bytes (bytes): The file bytes to be saved.
            content_type (str): The content type of the file.
            source (str): The source of the file, e.g. the file name or URL.
        """
        # save a file in a temporary folder
        extension = mimetypes.guess_extension(content_type)
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            temp_file.write(file_bytes)
            file_path = temp_file.name

        # upload a file to CheshireCat's file manager
        try:
            # finalize the source string so that its value is an acceptable file name even if the initial source is an URL
            source_finalized = (
                source.replace("://", "_").replace("/", "_").replace("\\", "_")
                if "://" in source
                else source
            )
            self.cat.file_manager.upload_file_to_storage(file_path, self.cat.agent_key, source_finalized)
        except Exception as e:
            log.error(f"Error while uploading file {file_path}: {e}")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)
