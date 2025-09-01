"""Hooks to modify the Cat's flow of execution.

Here is a collection of methods to hook into the Cat execution pipeline.

"""
from typing import Dict, List
import tiktoken

from cheshirecat.core_plugin.utils.memory import recall_relevant_memories_to_working_memory
from cheshirecat.core_plugin.utils.model_interactions import (
    ModelInteractionHandler,
    EmbedderModelInteraction,
)
from cheshirecat.exceptions import VectorMemoryError
from cheshirecat.log import log
from cheshirecat.mad_hatter.decorators import hook
from cheshirecat.memory.messages import MessageWhy
from cheshirecat.memory.utils import VectorMemoryCollectionTypes
from cheshirecat.utils import get_caller_info


# Called before cat bootstrap
@hook(priority=0)
def before_cat_bootstrap(cat) -> None:
    """
    Hook into the Cat start up.

    Bootstrapping is the process of loading the plugins, the natural language objects (e.g. the LLM), the memories,
    the *Main Agent*, the *Rabbit Hole* and the *White Rabbit*.

    This hook allows to intercept such process and is executed in the middle of plugins and
    natural language objects loading.

    This hook can be used to set or store variables to be propagated to subsequent loaded objects.

    Args:
        cat: CheshireCat
            Cheshire Cat instance.
    """
    pass  # do nothing


# Called after cat bootstrap
@hook(priority=0)
def after_cat_bootstrap(cat) -> None:
    """
    Hook into the end of the Cat start up.

    Bootstrapping is the process of loading the plugins, the natural language objects (e.g. the LLM), the memories,
    the *Main Agent*, the *Rabbit Hole* and the *White Rabbit*.

    This hook allows to intercept the end of such process and is executed right after the Cat has finished loading
    its components.

    This can be used to set or store variables to be shared further in the pipeline.

    Args:
        cat: CheshireCat
            Cheshire Cat instance.
    """
    pass  # do nothing


# Called when a user message arrives.
# Useful to edit/enrich user input (e.g. translation)
@hook(priority=0)
def before_cat_reads_message(user_message_json: Dict, cat) -> Dict:
    """
    Hook the incoming user's JSON dictionary.

    Allows to edit and enrich the incoming message received from the WebSocket connection.

    For instance, this hook can be used to translate the user's message before feeding it to the Cat.
    Another use case is to add custom keys to the JSON dictionary.

    The incoming message is a JSON dictionary with keys:
        {
            "text": message content
        }

    Args:
        user_message_json: Dict
            JSON dictionary with the message received from the chat.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        user_message_json: Dict
            Edited JSON dictionary that will be fed to the Cat.

    Notes
    -----
    For example:

        {
            "text": "Hello Cheshire Cat!",
            "custom_key": True
        }

    where "custom_key" is a newly added key to the dictionary to store any data.
    """
    # update conversation history (user turn)
    cat.working_memory.update_history(who="user", content=user_message_json)

    # recall declarative and procedural memories from vector collections and store them in working_memory
    try:
        recall_relevant_memories_to_working_memory(cat=cat, query=user_message_json["text"])
    except Exception as e:
        log.error(f"Agent id: {cat.agent_id}. Error during recall {e}")

        raise VectorMemoryError("An error occurred while recalling relevant memories.")

    return user_message_json


# What is the input to recall memories?
# Here you can do HyDE embedding, condense recent conversation or condition recall query on something else important to your AI
@hook(priority=0)
def cat_recall_query(user_message: str, cat) -> str:
    """
    Hook the semantic search query.

    This hook allows to edit the user's message used as a query for context retrieval from memories.
    As a result, the retrieved context can be conditioned editing the user's message.

    Args:
        user_message: str
            String with the text received from the user.
        cat: StrayCat
            Stray Cat instance to exploit the Cat's methods.

    Returns:
        Edited string to be used for context retrieval in memory. The returned string is further stored in the
        Working Memory at `cat.working_memory.recall_query`.

    Notes
    -----
    For example, this hook is a suitable to perform Hypothetical Document Embedding (HyDE).
    HyDE [1]_ strategy exploits the user's message to generate a hypothetical answer. This is then used to recall
    the relevant context from the memory.
    An official plugin is available to test this technique.

    References
    ----------
    [1] Gao, L., Ma, X., Lin, J., & Callan, J. (2022). Precise Zero-Shot Dense Retrieval without Relevance Labels.
       arXiv preprint arXiv:2212.10496.

    """
    # here we just return the latest user message as is
    return user_message


# Called just before the cat recalls memories.
@hook(priority=0)
def before_cat_recalls_memories(cat) -> None:
    """
    Hook into semantic search in memories.

    Allows to intercept when the Cat queries the memories using the embedded user's input.

    The hook is executed just before the Cat searches for the meaningful context in both memories
    and stores it in the *Working Memory*.

    Args:
        cat: StrayCat
            Stray Cat instance.

    """
    message = cat.working_memory.recall_query
    cat.working_memory.model_interactions.append(
        EmbedderModelInteraction(
            prompt=[message],
            source=get_caller_info(skip=1),
            input_tokens=len(tiktoken.get_encoding("cl100k_base").encode(message)),
        )
    )


@hook(priority=0)
def before_cat_recalls_declarative_memories(declarative_recall_config: Dict, cat) -> Dict:
    """
    Hook into semantic search in memories.

    Allows to intercept when the Cat queries the memories using the embedded user's input.

    The hook is executed just before the Cat searches for the meaningful context in both memories
    and stores it in the *Working Memory*.

    The hook return the values for maximum number (k) of items to retrieve from memory and the score threshold applied
    to the query in the vector memory (items with score under threshold are not retrieved)
    It also returns the embedded query (embedding) and the conditions on recall (metadata).

    Args:
        declarative_recall_config: Dict | RecallSettings
            Data needed to recall declarative memories
        cat: StrayCat
            Stray Cat instance.

    Returns:
        declarative_recall_config: Dict
            Edited dictionary that will be fed to the embedder.

    """
    return declarative_recall_config


@hook(priority=0)
def before_cat_recalls_procedural_memories(procedural_recall_config: Dict, cat) -> Dict:
    """
    Hook into semantic search in memories.

    Allows to intercept when the Cat queries the memories using the embedded user's input.

    The hook is executed just before the Cat searches for the meaningful context in both memories
    and stores it in the *Working Memory*.

    The hook return the values for maximum number (k) of items to retrieve from memory and the score threshold applied
    to the query in the vector memory (items with score under threshold are not retrieved)
    It also returns the embedded query (embedding) and the conditions on recall (metadata).

    Args:
        procedural_recall_config: Dict | RecallSettings
            Data needed to recall tools from procedural memory
        cat: StrayCat
            Stray Cat instance.

    Returns:
        procedural_recall_config: Dict
            Edited dictionary that will be fed to the embedder.

    """
    return procedural_recall_config


# Called just before the cat recalls memories.
@hook(priority=0)
def after_cat_recalls_memories(cat) -> None:
    """
    Hook after semantic search in memories.

    The hook is executed just after the Cat searches for the meaningful context in memories
    and stores it in the *Working Memory*.

    Args:
        cat: StrayCat
            Stray Cat instance.

    """
    pass  # do nothing


# Hook called just before sending response to a client.
@hook(priority=0)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
    """
    Hook the outgoing Cat's message.

    Allows to edit the JSON dictionary that will be sent to the client via WebSocket connection.

    This hook can be used to edit the message sent to the user or to add keys to the dictionary.

    Args:
        message: Dict
            JSON dictionary to be sent to the WebSocket client.
        agent_output: AgentOutput | None
            The output of the agent if an agent is used, None otherwise.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        message: Dict
            Edited JSON dictionary with the Cat's answer.

    Notes
    -----
    Default `message` is::
            {
                "type": "chat",
                "text": cat_message["output"],
                "image": cat_message["image"],
                "error": "...",
                "why": {
                    "input": cat_message["input"],
                    "intermediate_steps": [...],
                    "memory": {
                        "declarative": declarative_report
                        "procedural": procedural_report
                    },
                },
            }
    """
    memory = {str(c): [dict(d.document) | {
        "score": float(d.score) if d.score else None,
        "id": d.id,
    } for d in getattr(cat.working_memory, f"{c}_memories")] for c in VectorMemoryCollectionTypes}

    # why this response?
    message.why = MessageWhy(
        input=cat.working_memory.user_message.text,
        intermediate_steps=agent_output.intermediate_steps,
        memory=memory,
    )

    if agent_output.with_llm_error:
        cat.working_memory.pop_last_message_if_human()
    else:
        # update conversation history (AI turn)
        cat.working_memory.update_history(who="assistant", content=message)

    return message


@hook(priority=0)
def fast_reply(reply: str | None, cat) -> str | None:
    """
    This hook allows for an immediate response, bypassing memory recall and agent execution.
    It's useful for canned replies, custom LLM chains / agents, topic evaluation, direct LLM interaction and so on.

    Args:
        reply: str | None
            If you want to short-circuit the normal flow, return a string with the response to be sent to the user.
            If you want to continue with the normal flow, reply is None.
        cat : StrayCat
            Stray Cat instance.

    Returns:
        response : str | None
            If you want to short-circuit the normal flow, return a string with the response to be sent to the user.
            If you want to continue with the normal flow, return None.

    Examples
    --------
    Example 1: can't talk about this topic
    ```python
    # here you could use cat.llm to do topic evaluation
    if "dog" in cat.working_memory.user_message_json.text:
        return "You went out of topic. Can't talk about dog."
    ```
    """
    return reply


@hook(priority=0)
def llm_callbacks(callbacks: List, cat) -> List:
    """
    Add custom callbacks to the LangChain LLM/ChatModel. Here we add a token counter.

    Args:
        callbacks: List
            List of existing callbacks to be passed to the LLM/ChatModel
        cat:
            Stray Cat instance.

    Returns:
        callbacks: List
            Edited list of callbacks to be passed to the LLM/ChatModel
    """
    # Add a token counter to the callbacks
    caller = get_caller_info(skip=1)
    callbacks.append(ModelInteractionHandler(cat, caller))

    return callbacks
