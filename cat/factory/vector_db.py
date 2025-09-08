import socket
import sys
from abc import ABC, abstractmethod
import asyncio
from typing import Any, List, Iterable, Dict, Tuple, Type
from urllib.parse import urlparse
from pydantic import ConfigDict
from qdrant_client import AsyncQdrantClient
import os
import uuid
import aiofiles
import httpx
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    CreateAliasOperation,
    CreateAlias,
    OptimizersConfigDiff,
    PayloadSchemaType,
    Filter,
    HasIdCondition,
    Batch,
    FieldCondition,
    MatchValue,
    MatchText,
    SearchParams,
    QuantizationSearchParams,
    PointStruct as QdrantPointStruct,
)

from cat.factory.base_factory import BaseFactoryConfigModel, BaseFactory
from cat.log import log
from cat.memory.utils import (
    DocumentRecall,
    Payload,
    PointStruct,
    Record,
    ScoredPoint,
    UpdateResult,
    to_document_recall,
)


class BaseVectorDatabaseHandler(ABC):
    """
    Base class for vector database handlers.
    """
    _agent_id: str = None

    def __init__(self):
        self._client = None  # Placeholder for the database client

    @property
    def agent_id(self) -> str:
        return self._agent_id

    @agent_id.setter
    def agent_id(self, value: str):
        if not value:
            raise ValueError("Agent ID cannot be empty")
        self._agent_id = value

    @abstractmethod
    def tenant_field_condition(self) -> Any:
        """
        Returns the field condition for tenant filtering.
        """
        pass

    @abstractmethod
    async def initialize(self, embedder_name: str, embedder_size: int):
        """
        Initializes the vector database with the specified embedder name and size.
        Args:
            embedder_name: str, the name of the embedder to use.
            embedder_size: int, the size of the vector embeddings.
        """
        pass

    @abstractmethod
    def is_db_remote(self) -> bool:
        """
        Returns whether the vector database is remote or local.

        Returns:
            bool: True if the database is remote, False if local.
        """
        pass

    @abstractmethod
    async def close(self):
        """
        Closes the connection to the vector database.
        This method should be overridden by subclasses if they maintain a connection.
        """
        pass

    @abstractmethod
    async def delete_collection(self, collection_name: str, timeout: int | None = None):
        """
        Delete a collection from the vector database.

        Args:
            collection_name: Name of the collection to delete
            timeout: Optional timeout for the operation
        """
        pass

    @abstractmethod
    async def save_dump(self, collection_name: str, folder="dormouse/"):
        """
        Save a dump of the specified collection to a folder.

        Args:
            collection_name: Name of the collection to dump
            folder: Folder where the dump will be saved
        """
        pass

    @abstractmethod
    async def retrieve_points(self, collection_name:str, points: List) -> List[Record]:
        """
        Retrieve points from the collection by their ids

        Args:
            collection_name: the name of the collection to retrieve points from
            points: the ids of the points to retrieve

        Returns:
            the list of points
        """
        pass

    @abstractmethod
    async def add_point(
        self,
        collection_name: str,
        content: str,
        vector: Iterable,
        metadata: Dict = None,
        id: str | None = None,
        **kwargs,
    ) -> PointStruct | None:
        """Add a point (and its metadata) to the vectorstore.

        Args:
            collection_name: Name of the collection to add the point to.
            content: original text.
            vector: Embedding vector.
            metadata: Optional metadata dictionary associated with the text.
            id:
                Optional id to associate with the point. Id has to be an uuid-like string.

        Returns:
            PointStruct: The stored point.
        """
        pass

    @abstractmethod
    async def add_points(
        self, collection_name: str, payloads: List[Payload], vectors: List, ids: List | None = None
    ) -> UpdateResult:
        """
        Upsert memories in batch mode
        Args:
            collection_name: the name of the collection to upsert points into
            payloads: the payloads of the points
            vectors: the vectors of the points
            ids: the ids of the points, if not provided, they will be generated automatically using uuid4 hex strings

        Returns:
            the response of the upsert operation
        """
        pass

    @abstractmethod
    async def delete_points_by_metadata_filter(self, collection_name: str, metadata: Dict | None = None) -> UpdateResult:
        """
        Delete points from the collection by metadata filter.

        Args:
            collection_name: Name of the collection to delete points from.
            metadata: Optional metadata filter to select points for deletion.

        Returns:
            UpdateResult: The result of the delete operation.
        """
        pass

    @abstractmethod
    async def delete_points(self, collection_name: str, points_ids: List) -> UpdateResult:
        """
        Delete points from the collection by their ids.

        Args:
            collection_name: Name of the collection to delete points from.
            points_ids: List of point ids to delete.

        Returns:
            UpdateResult: The result of the delete operation.
        """
        pass

    @abstractmethod
    async def recall_memories_from_embedding(
        self,
        collection_name: str,
        embedding: List[float],
        metadata: Dict | None = None,
        k: int | None = 5,
        threshold: float | None = None,
    ) -> List[DocumentRecall]:
        """
        Retrieve memories from the collection based on an embedding vector. The memories are sorted by similarity to the
        embedding vector. The metadata filter is applied to the memories before retrieving them. The number of memories
        to retrieve is limited by the k parameter. The threshold parameter is used to filter out memories with a score
        below the threshold. The memories are returned as a list of tuples, where each tuple contains a Document, the
        similarity score, and the embedding vector of the memory. The Document contains the page content and metadata of
        the memory. The similarity score is a float between 0 and 1, where 1 is the highest similarity. The embedding
        vector is a list of floats. The list of tuples is sorted by similarity score in descending order. If the k
        parameter is None, all memories are retrieved. If the threshold parameter is None, no memories are filtered out.

        Args:
            collection_name: Name of the collection to search in.
            embedding: Embedding vector.
            metadata: Dictionary containing metadata filter.
            k: Number of memories to retrieve.
            threshold: Similarity threshold.

        Returns:
            List: List of DocumentRecall.
        """
        pass

    @abstractmethod
    async def recall_all_memories(self, collection_name: str) -> List[DocumentRecall]:
        """
        Retrieve the entire memories. It is similar to `recall_memories_from_embedding`, but without the embedding
        vector. Like `get_all_points`, it retrieves all the memories in the collection. The memories are returned in the
        same format as `recall_memories_from_embedding`.

        Args:
            collection_name: Name of the collection to retrieve memories from.

        Returns:
            List: List of DocumentRecall, like `recall_memories_from_embedding`, but with the nulled 2nd element
            (the score).

        See Also:
            VectorMemoryCollection.recall_memories_from_embedding
            VectorMemoryCollection.get_all_points
        """
    @abstractmethod
    async def get_all_points(
        self,
        collection_name: str,
        limit: int | None = None,
        offset: str | None = None,
        metadata: Dict | None = None,
    ) -> Tuple[List[Record], int | str | None]:
        """
        Retrieve all the points in the collection with an optional offset and limit.

        Args:
            collection_name: The name of the collection to retrieve points from.
            limit: The maximum number of points to retrieve.
            offset: The offset from which to start retrieving points.
            metadata: Optional metadata filter to apply to the points.

        Returns:
            Tuple: A tuple containing the list of points and the next offset.
        """
        pass

    @abstractmethod
    async def get_all_points_from_web(
        self, collection_name: str, limit: int | None = None, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        """
        Retrieve all the points in the collection with an optional offset and limit, specifically for web access.

        Args:
            collection_name: The name of the collection to retrieve points from.
            limit: The maximum number of points to retrieve.
            offset: The offset from which to start retrieving points.

        Returns:
            Tuple: A tuple containing the list of points and the next offset.
        """
        pass

    @abstractmethod
    async def get_all_points_from_files(
        self, collection_name: str, limit: int | None = None, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        """
        Retrieve all the points in the collection with an optional offset and limit, specifically for file access.

        Args:
            collection_name: The name of the collection to retrieve points from.
            limit: The maximum number of points to retrieve.
            offset: The offset from which to start retrieving points.

        Returns:
            Tuple: A tuple containing the list of points and the next offset.
        """
        pass

    @abstractmethod
    async def get_vectors_count(self, collection_name: str) -> int:
        """
        Get the count of vectors in the specified collection.

        Args:
            collection_name: The name of the collection to count vectors in.

        Returns:
            int: The number of vectors in the collection.
        """
        pass

    @abstractmethod
    async def destroy_all_points(self, collection_name: str) -> bool:
        """
        Destroy all points in the specified collection.

        Args:
            collection_name: The name of the collection to destroy points in.

        Returns:
            bool: True if the operation was successful, False otherwise.
        """
        pass

    @abstractmethod
    async def update_metadata(self, collection_name: str, points: List[PointStruct], metadata: Dict) -> UpdateResult:
        """
        Update the metadata of a point in the collection.

        Args:
            collection_name: The name of the collection to update points in.
            points: The points to update.
            metadata: The metadata to update.

        Returns:
            UpdateResult: The result of the update operation.
        """
        pass

    @abstractmethod
    async def get_embedder_size(self, embedder_name: str) -> int:
        """
        Get the size of the embedder.

        Args:
            embedder_name: The name of the embedder.

        Returns:
            int: The size of the embedder.
        """

    @abstractmethod
    async def create_collection(self, embedder_name: str, embedder_size: int, collection_name: str):
        """
        Create a new collection in the vector database.

        Args:
            embedder_name: Name of the embedder to use for the collection
            embedder_size: Size of the embedding vectors
            collection_name: Name of the collection to create
        """
        pass

    @abstractmethod
    async def get_collection_names(self) -> List[str]:
        """
        Get the list of collection names in the vector database.

        Returns:
            List[str]: List of collection names
        """
        pass


class QdrantHandler(BaseVectorDatabaseHandler):
    def __init__(
        self,
        host: str,
        port: int,
        api_key: str | None = None,
        client_timeout: int | None = 100,
        save_memory_snapshots: bool = False,
    ):
        super().__init__()

        self.save_memory_snapshots = save_memory_snapshots

        try:
            parsed_url = urlparse(host)
            qdrant_https = parsed_url.scheme == "https"
            qdrant_host = parsed_url.netloc + parsed_url.path
        except:
            qdrant_https = False
            qdrant_host = host

        qdrant_client_timeout = int(client_timeout) if client_timeout is not None else None

        s = None
        try:
            s = socket.socket()
            s.connect((qdrant_host, port))
        except:
            log.error(f"Qdrant does not respond to {qdrant_host}:{port}")
            sys.exit(-1)
        finally:
            if s:
                s.close()

        self._client = AsyncQdrantClient(
            host=qdrant_host,
            port=port,
            https=qdrant_https,
            api_key=api_key or None,
            prefer_grpc=True,
            force_disable_check_same_thread=True,
            timeout=qdrant_client_timeout,
        )

    def tenant_field_condition(self) -> FieldCondition:
        return FieldCondition(key="tenant_id", match=MatchValue(value=self.agent_id))

    # adapted from https://github.com/langchain-ai/langchain/blob/bfc12a4a7644cfc4d832cc4023086a7a5374f46a/libs/langchain/langchain/vectorstores/qdrant.py#L1941
    # see also https://github.com/langchain-ai/langchain/blob/bfc12a4a7644cfc4d832cc4023086a7a5374f46a/libs/langchain/langchain/vectorstores/qdrant.py#L1965
    def _build_condition(self, key: str, value: Any) -> List[FieldCondition]:
        out = []

        if isinstance(value, dict):
            for k, v in value.items():
                out.extend(self._build_condition(f"{key}.{k}", v))
        elif isinstance(value, list):
            for v in value:
                out.extend(self._build_condition(f"{key}[]" if isinstance(v, dict) else f"{key}", v))
        else:
            out.append(FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value)))

        return out

    def _build_metadata_conditions(self, metadata: Dict | None = None) -> List[FieldCondition]:
        conditions = [self.tenant_field_condition()]
        if metadata:
            conditions.extend([
                condition for key, value in metadata.items() for condition in self._build_condition(key, value)
            ])
        return conditions

    async def initialize(self, embedder_name: str, embedder_size: int):
        collection_name = "declarative"
        is_collection_existing = await self._check_collection_existence(collection_name)
        has_same_size = (
            await self._check_embedding_size(embedder_name, embedder_size, collection_name)
        ) if is_collection_existing else False
        if is_collection_existing and has_same_size:
            return

        # Memory snapshot saving can be turned off in the .env file with:
        # SAVE_MEMORY_SNAPSHOTS=false
        if self.save_memory_snapshots:
            # dump collection on disk before deleting
            await self.save_dump(collection_name)

        if is_collection_existing:
            await self._client.delete_collection(collection_name=collection_name)
            log.warning(f"Collection `{collection_name}` for the agent `{self.agent_id}` deleted")
        await self.create_collection(embedder_name, embedder_size, collection_name)

    async def _check_collection_existence(self, collection_name: str) -> bool:
        collection_names = await self.get_collection_names()
        if any(c == collection_name for c in collection_names):
            # collection exists. Do nothing
            log.info(f"Collection `{collection_name}` for the agent `{self.agent_id}` already present in vector store")
            return True

        return False

    def _get_local_alias(self, embedder_name: str, collection_name: str) -> str:
        return f"{embedder_name}_{collection_name}"

    async def _check_embedding_size(
        self, embedder_name: str, embedder_size: int, collection_name: str
    ) -> bool:
        # having the same size does not necessarily imply being the same embedder
        # having vectors with the same size but from different embedder in the same vector space is wrong
        same_size = (await self.get_embedder_size(embedder_name)) == embedder_size
        local_alias = self._get_local_alias(embedder_name, collection_name)

        existing_aliases = (await self._client.get_collection_aliases(collection_name=collection_name)).aliases

        if same_size and existing_aliases and local_alias == existing_aliases[0].alias_name:
            log.debug(f"Collection `{collection_name}` for the agent `{self.agent_id}` has the same embedder")
            return True

        log.warning(f"Collection `{collection_name}` for the agent `{self.agent_id}` has different embedder")
        return False

    async def create_collection(self, embedder_name: str, embedder_size: int, collection_name: str):
        log.warning(f"Creating collection `{collection_name}` for the agent `{self.agent_id}`...")

        try:
            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=embedder_size, distance=Distance.COSINE),
                # hybrid mode: original vector on Disk, quantized vector in RAM
                optimizers_config=OptimizersConfigDiff(memmap_threshold=20000, indexing_threshold=20000),
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
                        type=ScalarType.INT8, quantile=0.95, always_ram=True
                    )
                ),
                # shard_number=3,
            )
        except Exception as e:
            log.error(
                f"Error creating collection `{collection_name}` for the agent `{self.agent_id}`. Try setting a higher timeout value: {e}"
            )
            raise

        alias_name = self._get_local_alias(embedder_name, collection_name)
        log.warning(f"Creating alias `{alias_name}` for collection `{collection_name}` and the agent `{self.agent_id}`...")
        try:
            await self._client.update_collection_aliases(
                change_aliases_operations=[
                    CreateAliasOperation(
                        create_alias=CreateAlias(
                            collection_name=collection_name,
                            alias_name=alias_name,
                        )
                    )
                ]
            )
        except Exception as e:
            log.error(f"Error creating collection alias `{alias_name}` for collection `{collection_name}` and the agent `{self.agent_id}`: {e}")
            await self._client.delete_collection(collection_name)
            log.error(f"Collection `{collection_name}` for the agent `{self.agent_id}` deleted")
            raise e

        # if the client is remote, create an index on the tenant_id field
        if self.is_db_remote():
            log.warning(f"Creating payload index for collection `{collection_name}` and the agent `{self.agent_id}`...")
            try:
                await self._client.create_payload_index(
                    collection_name=collection_name,
                    field_name="tenant_id",
                    field_schema=PayloadSchemaType.KEYWORD
                )
            except Exception as e:
                log.error(f"Error when creating a schema index: {e}")

    async def close(self):
        if self._client and not self._client._client.closed:
            await self._client.close()

    async def delete_collection(self, collection_name: str, timeout: int | None = None):
        """
        Delete a collection from the vector database.

        Args:
            collection_name: Name of the collection to delete
            timeout: Optional timeout for the operation
        """
        await self._client.delete_collection(collection_name=collection_name, timeout=timeout)
        log.warning(f"Collection `{collection_name}` for the agent `{self.agent_id}` deleted")

    # dump collection on disk before deleting
    async def save_dump(self, collection_name: str, folder="dormouse/"):
        # only do snapshotting if using remote Qdrant
        if not self.is_db_remote():
            return

        host = self._client._client._host
        port = self._client._client._port

        if os.path.isdir(folder):
            log.debug("Directory dormouse exists")
        else:
            log.info("Directory dormouse does NOT exists, creating it.")
            os.mkdir(folder)

        snapshot_info = await self._client.create_snapshot(collection_name=collection_name)
        snapshot_url_in = (
            "http://"
            + str(host)
            + ":"
            + str(port)
            + "/collections/"
            + collection_name
            + "/snapshots/"
            + snapshot_info.name
        )
        snapshot_url_out = os.path.join(folder, snapshot_info.name)
        # rename snapshots for an easier restore in the future
        alias = (await self._client.get_collection_aliases(collection_name=collection_name)).aliases[0].alias_name

        async with httpx.AsyncClient() as client:
            response = await client.get(snapshot_url_in)
            async with aiofiles.open(snapshot_url_out, "wb") as f:
                await f.write(response.content)  # Write the content asynchronously

        new_name = os.path.join(folder, alias.replace("/", "-") + ".snapshot")
        os.rename(snapshot_url_out, new_name)

        for s in (await self._client.list_snapshots(collection_name=collection_name)):
            await self._client.delete_snapshot(collection_name=collection_name, snapshot_name=s.name)
        log.warning(f"Dump `{new_name}` for the agent `{self.agent_id}` completed")

    async def retrieve_points(self, collection_name:str, points: List) -> List[Record]:
        """
        Retrieve points from the collection by their ids

        Args:
            collection_name: the name of the collection to retrieve points from
            points: the ids of the points to retrieve

        Returns:
            the list of points
        """
        points_found, _ = await self._client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=self.agent_id)), HasIdCondition(has_id=points)]
            ),
            limit=len(points),
            with_payload=True,
            with_vectors=True,
        )

        return [Record(**point.model_dump()) for point in points_found]

    async def add_point(
        self,
        collection_name: str,
        content: str,
        vector: Iterable,
        metadata: Dict = None,
        id: str | None = None,
        **kwargs,
    ) -> PointStruct | None:
        """Add a point (and its metadata) to the vectorstore.

        Args:
            collection_name: Name of the collection to add the point to.
            content: original text.
            vector: Embedding vector.
            metadata: Optional metadata dictionary associated with the text.
            id:
                Optional id to associate with the point. Id has to be an uuid-like string.

        Returns:
            PointStruct: The stored point.
        """
        point = QdrantPointStruct(
            id=id or uuid.uuid4().hex,
            payload={
                "page_content": content,
                "metadata": metadata,
                "tenant_id": self.agent_id,
            },
            vector=vector,
        )

        update_status = await self._client.upsert(collection_name=collection_name, points=[point], **kwargs)

        if update_status.status == "completed":
            # returning stored point
            return PointStruct(**point.model_dump())

        return None

    # add points in collection
    async def add_points(
        self, collection_name: str, payloads: List[Payload], vectors: List, ids: List | None = None
    ) -> UpdateResult:
        """
        Upsert memories in batch mode
        Args:
            collection_name: the name of the collection to upsert points into
            payloads: the payloads of the points
            vectors: the vectors of the points
            ids: the ids of the points, if not provided, they will be generated automatically using uuid4 hex strings

        Returns:
            the response of the upsert operation
        """
        if not ids:
            ids = [uuid.uuid4().hex for _ in range(len(payloads))]

        if len(ids) != len(payloads) or len(ids) != len(vectors):
            raise ValueError("ids, payloads and vectors must have the same length")

        payloads = [{**p, **{"tenant_id": self.agent_id}} for p in payloads]
        points = Batch(ids=ids, payloads=payloads, vectors=vectors)

        res = await self._client.upsert(collection_name=collection_name, points=points)
        return UpdateResult(
            status=res.status,
            operation_id=res.operation_id,
        )

    async def delete_points_by_metadata_filter(self, collection_name: str, metadata: Dict | None = None) -> UpdateResult:
        conditions = self._build_metadata_conditions(metadata=metadata)

        res = await self._client.delete(collection_name=collection_name, points_selector=Filter(must=conditions))
        return UpdateResult(
            status=res.status,
            operation_id=res.operation_id,
        )

    # delete point in collection
    async def delete_points(self, collection_name: str, points_ids: List) -> UpdateResult:
        res = await self._client.delete(collection_name=collection_name, points_selector=points_ids)
        return UpdateResult(
            status=res.status,
            operation_id=res.operation_id,
        )

    # retrieve similar memories from embedding
    async def recall_memories_from_embedding(
        self,
        collection_name: str,
        embedding: List[float],
        metadata: Dict | None = None,
        k: int | None = 5,
        threshold: float | None = None,
    ) -> List[DocumentRecall]:
        """
        Retrieve memories from the collection based on an embedding vector. The memories are sorted by similarity to the
        embedding vector. The metadata filter is applied to the memories before retrieving them. The number of memories
        to retrieve is limited by the k parameter. The threshold parameter is used to filter out memories with a score
        below the threshold. The memories are returned as a list of tuples, where each tuple contains a Document, the
        similarity score, and the embedding vector of the memory. The Document contains the page content and metadata of
        the memory. The similarity score is a float between 0 and 1, where 1 is the highest similarity. The embedding
        vector is a list of floats. The list of tuples is sorted by similarity score in descending order. If the k
        parameter is None, all memories are retrieved. If the threshold parameter is None, no memories are filtered out.

        Args:
            collection_name: Name of the collection to search in.
            embedding: Embedding vector.
            metadata: Dictionary containing metadata filter.
            k: Number of memories to retrieve.
            threshold: Similarity threshold.

        Returns:
            List: List of DocumentRecall.
        """
        conditions = self._build_metadata_conditions(metadata=metadata)

        # retrieve memories
        query_response = await self._client.query_points(
            collection_name=collection_name,
            query=embedding,
            query_filter=Filter(must=conditions),
            with_payload=True,
            with_vectors=True,
            limit=k,
            score_threshold=threshold,
            search_params=SearchParams(
                quantization=QuantizationSearchParams(
                    ignore=False,
                    rescore=True,
                    oversampling=2.0,  # Available as of v1.3.0
                )
            ),
        )

        # convert Qdrant points to a structure containing langchain.Document and its information
        retrieved_points = [ScoredPoint(**point.model_dump()) for point in query_response.points]
        return [to_document_recall(m) for m in retrieved_points]

    async def recall_all_memories(self, collection_name: str) -> List[DocumentRecall]:
        all_points, _ = await self.get_all_points(collection_name)
        memories = [to_document_recall(p) for p in all_points]

        return memories

    async def _get_all_points(
        self,
        collection_name: str,
        scroll_filter: Filter,
        limit: int | None = None,
        offset: str | None = None,
        with_vectors: bool = True,
    ) -> Tuple[List[Record], int | str | None]:
        if limit is not None:
            # retrieving the points
            points_batch, next_offset = await self._client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                with_vectors=with_vectors,
                offset=offset,  # Start from the given offset, or the beginning if None.
                limit=limit  # Limit the number of points retrieved to the specified limit.
            )
            return [Record(**point.model_dump()) for point in points_batch], next_offset

        # retrieve all points without limit
        memory_points = []
        limit = 10000
        while True:
            # Get a batch of points
            points_batch, next_offset = await self._get_all_points(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                limit=limit,
                offset=offset,
                with_vectors=with_vectors,
            )

            # Add filtered points to our collection
            memory_points.extend(points_batch)

            # Check if we have more pages
            if next_offset is None:
                # No more pages
                break

            # Set offset for next iteration
            offset = next_offset

            # Optional: Add a small delay to avoid overwhelming the system
            await asyncio.sleep(0.1)
        return memory_points, None

    # retrieve all the points in the collection
    async def get_all_points(
        self,
        collection_name: str,
        limit: int | None = None,
        offset: str | None = None,
        metadata: Dict | None = None,
    ) -> Tuple[List[Record], int | str | None]:
        """
        Retrieve all the points in the collection with an optional offset and limit.

        Args:
            collection_name: The name of the collection to retrieve points from.
            limit: The maximum number of points to retrieve.
            offset: The offset from which to start retrieving points.
            metadata: Optional metadata filter to apply to the points.

        Returns:
            Tuple: A tuple containing the list of points and the next offset.
        """
        conditions = self._build_metadata_conditions(metadata)
        return await self._get_all_points(
            collection_name=collection_name, scroll_filter=Filter(must=conditions), limit=limit, offset=offset
        )

    async def get_all_points_from_web(
        self, collection_name: str, limit: int | None = None, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        conditions = [
            self.tenant_field_condition(),
            FieldCondition(
                key="metadata.source",
                match=MatchText(text="http")  # Regex for "starts with http"
            )
        ]

        return await self._get_all_points(
            collection_name=collection_name,
            scroll_filter=Filter(must=conditions),
            limit=limit,
            offset=offset,
            with_vectors=False,
        )

    async def get_all_points_from_files(
        self, collection_name: str, limit: int | None = None, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        filter_condition = Filter(
            must_not=[
                FieldCondition(
                    key="metadata.source",
                    match=MatchText(text="http")  # Regex for "starts with http"
                )
            ],
            must=[
                self.tenant_field_condition(),
                FieldCondition(
                    key="metadata.source",
                    match=MatchValue(value="^http")  # Regex for "starts with http"
                )
            ]
        )

        return await self._get_all_points(
            collection_name=collection_name,
            scroll_filter=filter_condition,
            limit=limit,
            offset=offset,
            with_vectors=False
        )

    async def get_vectors_count(self, collection_name: str) -> int:
        return (await self._client.count(
            collection_name=collection_name,
            count_filter=Filter(must=[self.tenant_field_condition()]),
        )).count

    async def destroy_all_points(self, collection_name: str) -> bool:
        try:
            await self._client.delete(
                collection_name=collection_name,
                points_selector=Filter(must=[self.tenant_field_condition()]),
            )
            return True
        except Exception as e:
            log.error(f"Error deleting collection `{collection_name}`, agent `{self.agent_id}`: {e}")
            return False

    async def update_metadata(self, collection_name: str, points: List[PointStruct], metadata: Dict) -> UpdateResult:
        qdrant_points = []
        for point in points:
            point.payload["metadata"] = {**point.payload["metadata"], **metadata}
            point.payload["tenant_id"] = self.agent_id
            qdrant_points.append(QdrantPointStruct(**point.model_dump()))
        res = await self._client.upsert(collection_name=collection_name, points=qdrant_points)
        return UpdateResult(
            status=res.status,
            operation_id=res.operation_id,
        )

    def is_db_remote(self) -> bool:
        return True

    async def get_embedder_size(self, embedder_name: str) -> int:
        embedder_size = (await self._client.get_collection(collection_name="declarative")).config.params.vectors.size
        return embedder_size

    async def get_collection_names(self) -> List[str]:
        collections_response = await self._client.get_collections()
        return [c.name for c in collections_response.collections]


class VectorDatabaseSettings(BaseFactoryConfigModel, ABC):
    save_memory_snapshots: bool = False

    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type:
        return BaseVectorDatabaseHandler


class QdrantConfig(VectorDatabaseSettings):
    host: str = "cheshire_cat_vector_memory"
    port: int = 6333
    api_key: str | None = None
    client_timeout: int | None = 100

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Remote Qdrant Vector Database",
            "description": "Configuration for Remote Qdrant Vector Database",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return QdrantHandler


class VectorDatabaseFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[VectorDatabaseSettings]]:
        list_vector_db_default = [QdrantConfig]

        list_vector_dbs = self._hook_manager.execute_hook(
            "factory_allowed_vector_databases", list_vector_db_default, cat=None
        )
        return list_vector_dbs

    @property
    def setting_category(self) -> str:
        return "vector_database"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return QdrantConfig

    @property
    def schema_name(self) -> str:
        return "vectorDatabaseName"
