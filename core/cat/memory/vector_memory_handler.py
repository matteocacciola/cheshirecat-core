import asyncio
import os
import uuid
from typing import Final, List, Iterable, Dict, Tuple, Any
import aiofiles
import httpx
from qdrant_client.async_qdrant_remote import AsyncQdrantRemote
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
)

from cat.db.vector_database import get_vector_db
from cat.env import get_env
from cat.log import log
from cat.memory.utils import (
    VectorMemoryCollectionTypes,
    VectorEmbedderSize,
    DocumentRecall,
    Payload,
    PointStruct,
    Record,
    UpdateResult,
    to_document_recall,
)


class VectorMemoryHandler:
    def __init__(self, agent_id: str):
        self.agent_id: Final = agent_id

        # connects to Qdrant and creates self._client attribute
        self._client: Final = get_vector_db()

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

    async def initialize(self, embedder_name: str, embedder_size: VectorEmbedderSize):
        for collection_name in VectorMemoryCollectionTypes:
            is_collection_existing = await self._check_collection_existence(str(collection_name))
            has_same_size = (
                await self._check_embedding_size(embedder_name, embedder_size, str(collection_name))
            ) if is_collection_existing else False
            if is_collection_existing and has_same_size:
                continue

            # Memory snapshot saving can be turned off in the .env file with:
            # SAVE_MEMORY_SNAPSHOTS=false
            if get_env("CCAT_SAVE_MEMORY_SNAPSHOTS") == "true":
                # dump collection on disk before deleting
                await self._save_dump(str(collection_name))

            if is_collection_existing:
                await self._client.delete_collection(collection_name=str(collection_name))
                log.warning(f"Collection \"{collection_name}\" deleted")
            await self._create_collection(embedder_name, embedder_size, str(collection_name))

    async def _check_collection_existence(self, collection_name: str) -> bool:
        collections_response = await self._client.get_collections()
        if any(c.name == collection_name for c in collections_response.collections):
            # collection exists. Do nothing
            log.info(f"Collection \"{collection_name}\" already present in vector store")
            return True

        return False

    def _get_local_alias(self, embedder_name: str, collection_name: str) -> str:
        return f"{embedder_name}_{collection_name}"

    async def _check_embedding_size(
        self, embedder_name: str, embedder_size: VectorEmbedderSize, collection_name: str
    ) -> bool:
        # having the same size does not necessarily imply being the same embedder
        # having vectors with the same size but from different embedder in the same vector space is wrong
        same_size = (
            (await self._client.get_collection(collection_name=collection_name)).config.params.vectors.size
            == embedder_size.text
        )
        local_alias = self._get_local_alias(embedder_name, collection_name)

        existing_aliases = (await self._client.get_collection_aliases(collection_name=collection_name)).aliases

        if same_size and existing_aliases and local_alias == existing_aliases[0].alias_name:
            log.debug(f"Collection \"{collection_name}\" has the same embedder")
            return True

        log.warning(f"Collection \"{collection_name}\" has different embedder")
        return False

    # create collection
    async def _create_collection(self, embedder_name: str, embedder_size: VectorEmbedderSize, collection_name: str):
        """
        Create a new collection in the vector database.

        Args:
            embedder_name: Name of the embedder to use for the collection
            embedder_size: Size of the embedding vectors
            collection_name: Name of the collection to create
        """

        log.warning(f"Creating collection \"{collection_name}\"...")

        try:
            await self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(
                    size=embedder_size.text, distance=Distance.COSINE
                ),
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
                f"Error creating collection {collection_name}. Try setting a higher timeout value in CCAT_QDRANT_CLIENT_TIMEOUT: {e}"
            )
            raise

        alias_name = self._get_local_alias(embedder_name, collection_name)
        log.warning(f"Creating alias {alias_name} for collection \"{collection_name}\"...")
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
            log.error(f"Error creating collection alias {alias_name} for collection {collection_name}: {e}")
            await self._client.delete_collection(collection_name)
            log.error(f"Collection {collection_name} deleted")
            raise

        # if the client is remote, create an index on the tenant_id field
        if self.is_db_remote():
            log.warning(f"Creating payload index for collection \"{collection_name}\"...")
            try:
                await self._client.create_payload_index(
                    collection_name=collection_name,
                    field_name="tenant_id",
                    field_schema=PayloadSchemaType.KEYWORD
                )
            except Exception as e:
                log.error(f"Error when creating a schema index: {e}")

    def is_db_remote(self) -> bool:
        return isinstance(self._client._client, AsyncQdrantRemote)

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
        log.warning(f"Collection \"{collection_name}\" deleted")

    # dump collection on disk before deleting
    async def _save_dump(self, collection_name: str, folder="dormouse/"):
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
        log.warning(f"Dump \"{new_name}\" completed")

    async def retrieve_points(self, collection_name:str, points: List) -> List[Record]:
        """
        Retrieve points from the collection by their ids

        Args:
            collection_name: the name of the collection to retrieve points from
            points: the ids of the points to retrieve

        Returns:
            the list of points
        """

        results = await self._client.scroll(
            collection_name=collection_name,
            scroll_filter=Filter(
                must=[FieldCondition(key="tenant_id", match=MatchValue(value=self.agent_id)), HasIdCondition(has_id=points)]
            ),
            limit=len(points),
            with_payload=True,
            with_vectors=True,
        )

        points_found, _ = results
        return points_found

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

        point = PointStruct(
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
            return point

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
        return res

    async def delete_points_by_metadata_filter(self, collection_name: str, metadata: Dict | None = None) -> UpdateResult:
        conditions = self._build_metadata_conditions(metadata=metadata)

        res = await self._client.delete(collection_name=collection_name, points_selector=Filter(must=conditions))
        return res

    # delete point in collection
    async def delete_points(self, collection_name: str, points_ids: List) -> UpdateResult:
        res = await self._client.delete(collection_name=collection_name, points_selector=points_ids)
        return res

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
        return [to_document_recall(m) for m in query_response.points]

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
            return await self._client.scroll(
                collection_name=collection_name,
                scroll_filter=scroll_filter,
                with_vectors=with_vectors,
                offset=offset,  # Start from the given offset, or the beginning if None.
                limit=limit  # Limit the number of points retrieved to the specified limit.
            )

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
            log.error(f"Error deleting collection {collection_name}, agent {self.agent_id}: {e}")
            return False

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
        for point in points:
            point.payload["metadata"] = {**point.payload["metadata"], **metadata}
            point.payload["tenant_id"] = self.agent_id
        return await self._client.upsert(collection_name=collection_name, points=points)
