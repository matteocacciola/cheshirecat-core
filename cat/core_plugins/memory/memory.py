import tiktoken

from cat.core_plugins.memory.models import EmbedderModelInteraction
from cat.core_plugins.memory.utils import recall_relevant_memories_to_working_memory
from cat.exceptions import VectorMemoryError
from cat.log import log
from cat.mad_hatter.decorators import hook
from cat.memory.messages import UserMessage
from cat.utils import get_caller_info, dispatch


@hook(priority=1)
def before_cat_reads_message(user_message: UserMessage, cat) -> UserMessage:
    # recall declarative memory from vector collections and store it in working_memory
    try:
        r = dispatch(
            recall_relevant_memories_to_working_memory,
            cat=cat,
            query=user_message.text,
        )
        if hasattr(r, "__await__"):
            import asyncio

            asyncio.get_event_loop().run_until_complete(r)
    except Exception as e:
        log.error(f"Agent id: {cat.agent_id}. Error during recall {e}")

        raise VectorMemoryError("An error occurred while recalling relevant memories.")

    return user_message


@hook(priority=1)
def before_cat_recalls_memories(cat) -> None:
    message = cat.working_memory.recall_query
    cat.working_memory.model_interactions.append(
        EmbedderModelInteraction(
            prompt=[message],
            source=get_caller_info(skip=1),
            input_tokens=len(tiktoken.get_encoding("cl100k_base").encode(message)),
        )
    )
