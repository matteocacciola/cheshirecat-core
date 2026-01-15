"""Hooks to modify the Cat's *Agent*.

Here is a collection of methods to hook into the *Agent* execution pipeline.

"""
from typing import List

from cat import hook, AgenticWorkflowOutput


@hook(priority=0)
def agent_fast_reply(cat) -> AgenticWorkflowOutput | None:
    """
    This hook allows for a custom response after memory recall, skipping default agent execution.
    It's useful for custom agent logic or when you want to use recalled memories but avoid the main agent.

    Args:
        cat (StrayCat): Stray Cat instance.

    Returns:
        response (AgentOutput): If you want to bypass the main agent, return an AgenticWorkflowOutput with a valid `output` key.
            Return None to continue with normal execution.
            See below for examples of Cat response

    Examples
    --------

    Example 1: don't remember (no uploaded documents about topic)
    ```python
    num_declarative_memories = len( cat.working_memory.declarative_memories )
    if num_declarative_memories == 0:
        return AgenticWorkflowOutput(output="Sorry, I have no memories about that.")
    ```
    """
    return None


@hook(priority=0)
def agent_allowed_tools(allowed_tools: List[str], cat) -> List[str]:
    """
    Hook the allowed tools.

    Allows to decide which tools end up in the *Agent* prompt.

    To decide, you can filter the list of tools' names, but you can also check the context in `cat.working_memory`
    and launch custom chains with `cat.llm`.

    Args:
        allowed_tools (List[str]): List of tools that are allowed to be used by the *
        cat (StrayCat): Stray Cat instance.

    Returns:
        tools (List[str]): List of allowed Langchain tools.
    """
    return allowed_tools
