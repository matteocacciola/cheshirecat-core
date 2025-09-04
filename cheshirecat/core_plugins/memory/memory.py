from typing import Dict
import tiktoken

from cheshirecat.core_plugins.memory.models import EmbedderModelInteraction
from cheshirecat.core_plugins.memory.utils import recall_relevant_memories_to_working_memory
from cheshirecat.exceptions import VectorMemoryError
from cheshirecat.log import log
from cheshirecat.mad_hatter.decorators import hook
from cheshirecat.memory.messages import UserMessage
from cheshirecat.utils import get_caller_info


@hook(priority=1)
def before_cat_reads_message(user_message: UserMessage, cat) -> UserMessage:
    # update conversation history (user turn)
    cat.working_memory.update_history(who="user", content=user_message)

    # recall declarative memory from vector collections and store it in working_memory
    try:
        recall_relevant_memories_to_working_memory(cat=cat, query=user_message.text)
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


@hook(priority=1)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
    if agent_output.with_llm_error:
        cat.working_memory.pop_last_message_if_human()
    else:
        # update conversation history (AI turn)
        cat.working_memory.update_history(who="assistant", content=message)

    return message
