from typing import List, Dict

from cat import utils
from cat.core_plugins.memory.models import RecallSettings
from cat.log import log
from cat.memory.working_memory import DocumentRecall
from cat.memory.utils import VectorMemoryCollectionTypes


async def recall(
    cat: "StrayCat",
    query: List[float],
    collection_name: str,
    k: int | None = 5,
    threshold: int | None = None,
    metadata: Dict | None = None,
) -> List[DocumentRecall]:
    """
    This is a proxy method to perform search in a vector memory collection.
    The method allows retrieving information from one specific vector memory collection with custom parameters.
    The Cat uses this method internally to recall the relevant memories to Working Memory every user's chat
    interaction.
    This method is useful also to perform a manual search in hook and tools.

    Args:
        cat: StrayCat
            The StrayCat instance.
        query: List[float]
            The search query, passed as embedding vector.
            Please first run cheshire_cat.embedder.embed_query(query) if you have a string query to pass here.
        collection_name: str
            The name of the collection to perform the search.
            Available collection is: *declarative*.
        k: int | None
            The number of memories to retrieve.
            If `None` retrieves all the available memories.
        threshold: float | None
            The minimum similarity to retrieve a memory.
            Memories with lower similarity are ignored.
        metadata: Dict
            Additional filter to retrieve memories with specific metadata.

    Returns:
        memories: List[DocumentRecall]
            List of retrieved memories.
    """
    cheshire_cat = cat.cheshire_cat

    if collection_name not in VectorMemoryCollectionTypes:
        memory_collections = ', '.join([str(c) for c in VectorMemoryCollectionTypes])
        error_message = f"{collection_name} is not a valid collection. Available collections: {memory_collections}"

        log.error(error_message)
        raise ValueError(error_message)

    if k:
        memories = await cheshire_cat.vector_memory_handler.recall_memories_from_embedding(
            collection_name, query, metadata, k, threshold
        )
    else:
        memories = await cheshire_cat.vector_memory_handler.recall_all_memories(collection_name)

    setattr(cat.working_memory, f"{collection_name}_memories", memories)
    return memories


def recall_relevant_memories_to_working_memory(cat: "StrayCat", query: str):
    """
    Retrieve context from memory.
    The method retrieves the relevant memories from the vector collections that are given as context to the LLM.
    Recalled memories are stored in the working memory.

    Args:
        cat: StrayCat
            The StrayCat instance.
        query: str
            The query used to make a similarity search in the Cat's vector memories.

    See Also:
        cat_recall_query
        before_cat_recalls_memories
        after_cat_recalls_memories

    Examples
    --------
    Recall memories from custom query
    >> cat.recall_relevant_memories_to_working_memory(query="What was written on the bottle?")

    Notes
    -----
    The user's message is used as a query to make a similarity search in the Cat's vector memories.
    Five hooks allow customizing the recall pipeline before and after it is done.
    """
    cheshire_cat = cat.cheshire_cat
    plugin_manager = cat.plugin_manager

    # We may want to search in memory. If a query is not provided, use the user's message as the query
    recall_query = plugin_manager.execute_hook("cat_recall_query", query, cat=cat)
    log.info(f"Agent id: {cat.agent_id}. Recall query: '{recall_query}'")

    # Embed recall query
    recall_query_embedding = cheshire_cat.embedder.embed_query(recall_query)

    # keep track of embedder model usage
    cat.working_memory.recall_query = recall_query

    # hook to do something before recall begins
    plugin_manager.execute_hook("before_cat_recalls_memories", cat=cat)

    # Setting default recall configs for each memory + hooks to change recall configs for each memory
    metadata = cat.working_memory.user_message.get("metadata", {})
    for memory_type in VectorMemoryCollectionTypes:
        config = RecallSettings(embedding=recall_query_embedding, metadata=metadata)

        utils.dispatch_event(
            recall,
            cat=cat,
            query=config.embedding,
            collection_name=str(memory_type),
            k=config.k,
            threshold=config.threshold,
            metadata=config.metadata,
        )

    # hook to modify/enrich retrieved memories
    plugin_manager.execute_hook("after_cat_recalls_memories", cat=cat)
