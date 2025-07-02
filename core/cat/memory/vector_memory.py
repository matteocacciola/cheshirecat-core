from typing import Dict

from cat.memory.utils import VectorMemoryCollectionTypes, VectorEmbedderSize
from cat.memory.vector_memory_collection import VectorMemoryCollection
from cat.memory.vector_memory_handler import VectorMemoryHandler
from cat.utils import dispatch_event


class VectorMemory:
    def __init__(self, agent_id: str) -> None:
        # Set the vector memory handler with the embedder name and size
        self.vector_memory_handler = VectorMemoryHandler(agent_id)

        # Dictionary containing all vector collections
        self.collections: Dict[str, VectorMemoryCollection] = {}

        # Create vector collections
        # - Episodic memory will contain user and eventually cat utterances
        # - Declarative memory will contain uploaded documents' content
        # - Procedural memory will contain tools and knowledge on how to do things
        for collection_name in VectorMemoryCollectionTypes:
            # Instantiate collection
            collection = VectorMemoryCollection(
                vector_memory_handler=self.vector_memory_handler, collection_name=str(collection_name)
            )

            # Update dictionary containing all collections
            # Useful for cross-searching and to create/use collections from plugins
            self.collections[str(collection_name)] = collection

            # Have the collection as an instance attribute
            # (i.e. do things like cat.memory.vectors.declarative.something())
            setattr(self, str(collection_name), collection)

    async def initialize(self, embedder_name: str, embedder_size: VectorEmbedderSize):
        await self.vector_memory_handler.initialize(embedder_name, embedder_size)

    async def destroy_collections(self) -> None:
        for c in VectorMemoryCollectionTypes:
            await self.collections[str(c)].destroy_all_points()
