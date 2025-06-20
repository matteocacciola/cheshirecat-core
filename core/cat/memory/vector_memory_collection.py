import asyncio
import uuid
from typing import Any, List, Iterable, Dict, Tuple, Final
from qdrant_client.qdrant_remote import QdrantRemote
from qdrant_client.http.models import (
    Batch,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
    MatchText,
    SearchParams,
    QuantizationSearchParams,
    Record,
    UpdateResult,
    HasIdCondition,
    Payload,
)

from cat.db.vector_database import get_vector_db
from cat.log import log
from cat.memory.utils import DocumentRecall, to_document_recall


class VectorMemoryCollection:
    def __init__(self, agent_id: str, collection_name: str):
        self.agent_id: Final[str] = agent_id

        # Set attributes (metadata on the embedder are useful because it may change at runtime)
        self.collection_name: Final[str] = collection_name

        # connects to Qdrant and creates self.client attribute
        self.client: Final = get_vector_db()

    def _tenant_field_condition(self) -> FieldCondition:
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
        conditions = [self._tenant_field_condition()]
        if metadata:
            conditions.extend([
                condition for key, value in metadata.items() for condition in self._build_condition(key, value)
            ])
        return conditions

    async def get_payload_indexes(self) -> Dict:
        """
        Retrieve the indexes configured on the collection.

        Returns:
            Dictionary with the configuration of the indexes
        """
        collection_info = await self.client.get_collection(collection_name=self.collection_name)
        return collection_info.payload_schema

    async def retrieve_points(self, points: List) -> List[Record]:
        """
        Retrieve points from the collection by their ids

        Args:
            points: the ids of the points to retrieve

        Returns:
            the list of points
        """

        results = await self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(must=[self._tenant_field_condition(), HasIdCondition(has_id=points)]),
            limit=len(points),
            with_payload=True,
            with_vectors=True,
        )

        points_found, _ = results
        return points_found

    async def add_point(
        self,
        content: str,
        vector: Iterable,
        metadata: Dict = None,
        id: str | None = None,
        **kwargs,
    ) -> PointStruct | None:
        """Add a point (and its metadata) to the vectorstore.

        Args:
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

        update_status = await self.client.upsert(collection_name=self.collection_name, points=[point], **kwargs)

        if update_status.status == "completed":
            # returning stored point
            return point

        return None

    # add points in collection
    async def add_points(self, payloads: List[Payload], vectors: List, ids: List | None = None):
        """
        Upsert memories in batch mode
        Args:
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

        res = await self.client.upsert(collection_name=self.collection_name, points=points)
        return res

    async def delete_points_by_metadata_filter(self, metadata: Dict | None = None) -> UpdateResult:
        conditions = self._build_metadata_conditions(metadata)

        res = await self.client.delete(collection_name=self.collection_name, points_selector=Filter(must=conditions))
        return res

    # delete point in collection
    async def delete_points(self, points_ids: List) -> UpdateResult:
        res = await self.client.delete(collection_name=self.collection_name, points_selector=points_ids)
        return res

    # retrieve similar memories from embedding
    async def recall_memories_from_embedding(
        self, embedding: List[float], metadata: Dict | None = None, k: int | None = 5, threshold: float | None = None
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
            embedding: Embedding vector.
            metadata: Dictionary containing metadata filter.
            k: Number of memories to retrieve.
            threshold: Similarity threshold.

        Returns:
            List: List of DocumentRecall.
        """

        conditions = self._build_metadata_conditions(metadata)

        # retrieve memories
        query_response = await self.client.query_points(
            collection_name=self.collection_name,
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

    async def recall_all_memories(self) -> List[DocumentRecall]:
        """
        Retrieve the entire memories. It is similar to `recall_memories_from_embedding`, but without the embedding
        vector. Like `get_all_points`, it retrieves all the memories in the collection. The memories are returned in the
        same format as `recall_memories_from_embedding`.

        Returns:
            List: List of DocumentRecall, like `recall_memories_from_embedding`, but with the nulled 2nd element
            (the score).

        See Also:
            VectorMemoryCollection.recall_memories_from_embedding
            VectorMemoryCollection.get_all_points
        """

        all_points, _ = await self.get_all_points()
        memories = [to_document_recall(p) for p in all_points]

        return memories

    async def _get_all_points(
        self, scroll_filter: Filter, limit: int | None = None, offset: str | None = None, with_vectors: bool = True
    ) -> Tuple[List[Record], int | str | None]:
        if limit is not None:
            # retrieving the points
            return await self.client.scroll(
                collection_name=self.collection_name,
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
                scroll_filter, limit=limit, offset=offset, with_vectors=with_vectors
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
        self, limit: int | None = None, offset: str | None = None, metadata: Dict | None = None
    ) -> Tuple[List[Record], int | str | None]:
        """
        Retrieve all the points in the collection with an optional offset and limit.

        Args:
            limit: The maximum number of points to retrieve.
            offset: The offset from which to start retrieving points.
            metadata: Optional metadata filter to apply to the points.

        Returns:
            Tuple: A tuple containing the list of points and the next offset.
        """

        conditions = self._build_metadata_conditions(metadata)
        return await self._get_all_points(Filter(must=conditions), limit=limit, offset=offset)

    async def get_all_points_from_web(
        self, limit: int | None = None, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        conditions = [
            self._tenant_field_condition(),
            FieldCondition(
                key="metadata.source",
                match=MatchText(text="http")  # Regex for "starts with http"
            )
        ]

        return await self._get_all_points(Filter(must=conditions), limit=limit, offset=offset, with_vectors=False)

    async def get_all_points_from_files(
        self, limit: int | None = None, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        filter_condition = Filter(
            must_not=[
                FieldCondition(
                    key="metadata.source",
                    match=MatchText(text="http")  # Regex for "starts with http"
                )
            ],
            must=[
                self._tenant_field_condition(),
                FieldCondition(
                    key="metadata.source",
                    match=MatchValue(value="^http")  # Regex for "starts with http"
                )
            ]
        )

        return await self._get_all_points(filter_condition, limit=limit, offset=offset, with_vectors=False)

    def db_is_remote(self):
        return isinstance(self.client._client, QdrantRemote)

    async def get_vectors_count(self) -> int:
        return (await self.client.count(
            collection_name=self.collection_name,
            count_filter=Filter(must=[self._tenant_field_condition()]),
        )).count

    async def destroy_all_points(self) -> bool:
        try:
            await self.client.delete(
                collection_name=self.collection_name,
                points_selector=Filter(must=[self._tenant_field_condition()]),
            )
            return True
        except Exception as e:
            log.error(f"Error deleting collection {self.collection_name}, agent {self.agent_id}: {e}")
            return False

    async def update_metadata(self, points: List[PointStruct], metadata: Dict) -> UpdateResult:
        """
        Update the metadata of a point in the collection.

        Args:
            points: The points to update.
            metadata: The metadata to update.

        Returns:
            UpdateResult: The result of the update operation.
        """
        for point in points:
            point.payload["metadata"] = {**point.payload["metadata"], **metadata}
            point.payload["tenant_id"] = self.agent_id
        return await self.client.upsert(collection_name=self.collection_name, points=points)
