from typing import List, Iterable, Dict, Tuple, Final

from cat.memory.utils import DocumentRecall, Payload, PointStruct, Record, UpdateResult, to_document_recall
from cat.memory.vector_memory_handler import VectorMemoryHandler


class VectorMemoryCollection:
    def __init__(self, vector_memory_handler: VectorMemoryHandler, collection_name: str):
        self.vector_memory_handler: Final[VectorMemoryHandler] = vector_memory_handler

        # Set attributes (metadata on the embedder are useful because it may change at runtime)
        self.collection_name: Final[str] = collection_name

    async def retrieve_points(self, points: List) -> List[Record]:
        """
        Retrieve points from the collection by their ids

        Args:
            points: the ids of the points to retrieve

        Returns:
            the list of points
        """

        points_found = await self.vector_memory_handler.retrieve_points(self.collection_name, points)

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

        point = await self.vector_memory_handler.add_point(
            collection_name=self.collection_name,
            content=content,
            vector=vector,
            metadata=metadata,
            id=id,
            **kwargs,
        )

        return point

    # add points in collection
    async def add_points(self, payloads: List[Payload], vectors: List, ids: List | None = None) -> UpdateResult:
        """
        Upsert memories in batch mode
        Args:
            payloads: the payloads of the points
            vectors: the vectors of the points
            ids: the ids of the points, if not provided, they will be generated automatically using uuid4 hex strings

        Returns:
            the response of the upsert operation
        """

        res = await self.vector_memory_handler.add_points(
            collection_name=self.collection_name,
            payloads=payloads,
            vectors=vectors,
            ids=ids,
        )

        return res

    async def delete_points_by_metadata_filter(self, metadata: Dict | None = None) -> UpdateResult:
        res = await self.vector_memory_handler.delete_points_by_metadata_filter(
            collection_name=self.collection_name, metadata=metadata
        )

        return res

    # delete point in collection
    async def delete_points(self, points_ids: List) -> UpdateResult:
        res = await self.vector_memory_handler.delete_points(
            collection_name=self.collection_name, points_ids=points_ids
        )
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

        res = await self.vector_memory_handler.recall_memories_from_embedding(
            collection_name=self.collection_name,
            metadata=metadata,
            embedding=embedding,
            k=k,
            threshold=threshold,
        )
        return res

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

    # retrieve all the points in the collection
    async def get_all_points(
        self, limit: int | None = None, offset: str | None = None, metadata: Dict | None = None
    ) -> Tuple[List[Record], int | str | None]:
        res = await self.vector_memory_handler.get_all_points(
            collection_name=self.collection_name,
            limit=limit,
            offset=offset,
            metadata=metadata,
        )

        return res

    async def get_all_points_from_web(
        self, limit: int | None = None, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        res = await self.vector_memory_handler.get_all_points_from_web(
            collection_name=self.collection_name,
            limit=limit,
            offset=offset,
        )

        return res

    async def get_all_points_from_files(
        self, limit: int | None = None, offset: str | None = None
    ) -> Tuple[List[Record], int | str | None]:
        res = await self.vector_memory_handler.get_all_points_from_files(
            collection_name=self.collection_name,
            limit=limit,
            offset=offset,
        )

        return res

    async def get_vectors_count(self) -> int:
        res = await self.vector_memory_handler.get_vectors_count(collection_name=self.collection_name)
        return res

    async def destroy_all_points(self) -> bool:
        res = await self.vector_memory_handler.destroy_all_points(collection_name=self.collection_name)
        return res

    async def update_metadata(self, points: List[PointStruct], metadata: Dict) -> UpdateResult:
        """
        Update the metadata of a point in the collection.

        Args:
            points: The points to update.
            metadata: The metadata to update.

        Returns:
            UpdateResult: The result of the update operation.
        """

        res = await self.vector_memory_handler.update_metadata(
            collection_name=self.collection_name, points=points, metadata=metadata
        )

        return res
