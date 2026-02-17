"""Hooks to modify the Cat's flow of execution.

Here is a collection of methods to hook into the Cat execution pipeline.

"""
from typing import Dict, List

from cat import hook, UserMessage, RecallSettings
from cat.core_plugins.base_plugin.registry import CheshireCatPluginRegistry


@hook(priority=0)
def before_lizard_bootstrap(lizard) -> None:
    """
    Executes actions that need to be performed before the lizard bootstrap process.

    This hook function is called with a configurable priority and is used to execute any preparatory operations
    required before the main bootstrap logic for the lizard application starts.

    Args:
        lizard: An object that provides context or data needed during the bootstrap preparation process. The exact usage and required attributes of the object depend on the implementation details of the bootstrap logic.
    """
    pass


@hook(priority=999)
def after_lizard_bootstrap(lizard) -> None:
    """
    Executes actions that need to be performed after the lizard bootstrap process.

    This hook function is called with a configurable priority and is used to execute any preparatory operations
    required after the main bootstrap logic for the lizard application starts.

    Args:
        lizard: An object that provides context or data needed during the bootstrap preparation process. The exact usage and required attributes of the object depend on the implementation details of the bootstrap logic.
    """
    lizard.plugin_registry = CheshireCatPluginRegistry()


@hook(priority=0)
def before_lizard_shutdown(lizard) -> None:
    """
    This function is a hook that gets called before the Lizard system shuts down. Its purpose is to perform any necessary
    operations or cleanup tasks related to the provided cat before the shutdown process begins.

    Args:
        lizard: The object that might need specific operations to be performed before the shutdown.
    """
    lizard.plugin_registry = None


@hook(priority=0)
def lizard_notify_plugin_installation(plugin_id: str, plugin_path: str, lizard) -> None:
    """
    Handles the notification process when a plugin is installed.

    This function is triggered when a plugin is installed and a hook is activated. The notification ensures that
    relevant stakeholders, systems, or components are informed about the installation event.

    Args:
        plugin_id: The ID of the plugin that is being installed.
        plugin_path: The path to the plugin's installation directory.
        lizard: The specific category or context associated with the installed plugin.
    """
    pass


@hook(priority=0)
def lizard_notify_plugin_uninstallation(plugin_id: str, lizard) -> None:
    """
    Handles the notification process when a plugin is installed.

    This function is triggered when a plugin is installed and a hook is de-activated. The notification ensures that
    relevant stakeholders, systems, or components are informed about the uninstallation event.

    Args:
        plugin_id: The ID of the plugin that is being uninstalled.
        lizard: The specific category or context associated with the uninstalled plugin.
    """
    pass


# Called before cat bootstrap
@hook(priority=0)
def before_cat_bootstrap(cat) -> None:
    """
    Hook into the Cat start up.

    Bootstrapping is the process of loading the plugins, the natural language objects (e.g. the LLM), the memories, etc.
    This hook allows to intercept such process and is executed in the middle of plugins and
    natural language objects loading.

    This hook can be used to set or store variables to be propagated to subsequent loaded objects.

    Args:
        cat (CheshireCat): Cheshire Cat instance.
    """
    pass  # do nothing


# Called after cat bootstrap
@hook(priority=0)
def after_cat_bootstrap(cat) -> None:
    """
    Hook into the end of the Cat start up.

    Bootstrapping is the process of loading the plugins, the natural language objects (e.g. the LLM), the memories, etc.
    This hook allows to intercept the end of such process and is executed right after the Cat has finished loading
    its components.

    This can be used to set or store variables to be shared further in the pipeline.

    Args:
        cat (CheshireCat): Cheshire Cat instance.
    """
    pass  # do nothing


# Called when a user message arrives.
# Useful to edit/enrich user input (e.g. translation)
@hook(priority=0)
def before_cat_reads_message(user_message: UserMessage, cat) -> UserMessage:
    """
    Hook the incoming user's JSON dictionary.

    Allows to edit and enrich the incoming message received from the WebSocket connection.

    For instance, this hook can be used to translate the user's message before feeding it to the Cat.
    Another use case is to add custom keys to the JSON dictionary.

    The incoming message is a JSON-like variable which can be handled as an object or a dictionary with keys:
        {
            "text": message content
        }

    Args:
        user_message (UserMessage): JSON-like variable with the message received from the chat.
        cat (StrayCat): Stray Cat instance.

    Returns:
        user_message (UserMessage): Edited JSON-like variable with the message to be processed by the Cat

    Notes
    -----
    For example:

        {
            "text": "Hello Cheshire Cat!",
            "custom_key": True
        }

    where "custom_key" is a newly added key to the dictionary to store any data.
    """
    return user_message


# Called just before the cat recalls memories.
@hook(priority=0)
def before_cat_recalls_memories(config: RecallSettings, cat) -> RecallSettings:
    """
    Hook into semantic search in memories.

    Allows intercepting when the Cat queries the memories using the embedded user's input.

    The hook is executed just before the Cat searches for the meaningful context in both memories
    and stores it in the *Working Memory*.

    Args:
        config (Dict): The configuration dictionary for retrieval of memories.
        cat (StrayCat): Stray Cat instance.

    Returns:
        The configuration dictionary for retrieval of memories.
    """
    return config


# Called just before the cat recalls memories.
@hook(priority=0)
def after_cat_recalls_memories(config: RecallSettings, cat) -> None:
    """
    Hook after a semantic search in memories.

    The hook is executed just after the Cat searches for the meaningful context in memories
    and stores it in the *Working Memory*.

    Args:
        config (RecallSettings): The configuration dictionary for retrieval of memories.
        cat (StrayCat): Stray Cat instance.
    """
    pass


# Hook called just before sending response to a client.
@hook(priority=0)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
    """
    Hook the outgoing Cat's message.

    Allows editing the JSON dictionary that will be sent to the client via WebSocket connection.

    This hook can be used to edit the message sent to the user or to add keys to the dictionary.

    Args:
        message (Dict): JSON dictionary to be sent to the WebSocket client.
        agent_output (AgentOutput): The output of the agent.
        cat (StrayCat): Stray Cat instance.

    Returns:
        message (Dict): Edited JSON dictionary with the Cat's answer.

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
                    },
                },
            }
    """
    return message


@hook(priority=0)
def fast_reply(reply: str | None, cat) -> str | None:
    """
    This hook allows for an immediate response, bypassing memory recall and agent execution.
    It's useful for canned replies, custom LLM chains / agents, topic evaluation, direct LLM interaction and so on.

    Args:
        reply (str | None): If you want to short-circuit the normal flow, return a string with the response to be sent
        to the user. If you want to continue with the normal flow, reply is None.
        cat (StrayCat): Stray Cat instance.

    Returns:
        response (str | None): If you want to short-circuit the normal flow, return a string with the response to be
        sent to the user. If you want to continue with the normal flow, return None.

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
        callbacks (List): List of existing callbacks to be passed to the LLM/ChatModel
        cat (StrayCat): Stray Cat instance.

    Returns:
        callbacks (List): Edited list of callbacks to be passed to the LLM/ChatModel
    """
    return callbacks
