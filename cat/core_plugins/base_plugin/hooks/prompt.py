"""Hooks to modify the prompts.

Here is a collection of methods to hook the prompts components that instruct the *Agent*.

"""
from typing import Dict, Any

from cat.mad_hatter.decorators import hook


@hook(priority=0)
def agent_prompt_prefix(prompt: str, cat) -> str:
    """Hook the main prompt prefix.

    Allows to edit the prefix of the *Main Prompt* that the Cat feeds to the *Agent*.
    It describes the personality of your assistant and its general task.

    Args:
        prompt: str
            Main / System prompt with personality and general task to be accomplished.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        prompt: str
            Main / System prompt.

    Notes
    -----
    The default prompt describe who the AI is and how it is expected to answer the user.
    """
    return prompt


@hook(priority=0)
def agent_prompt_variables(variables: Dict[str, Any], cat) -> Dict[str, Any]:
    """Hook the main prompt variables.
    Allows to edit the variables that will be used to format the *Main Prompt* that the Cat feeds to the *Agent*.

    Args:
        variables: Dict[str, Any]
            The variables that will be used to format the *Main Prompt*.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        variables: Dict[str, Any]
            The variables that will be used to format the *Main Prompt*.

    Notes
    -----
    The default variables are:
    - `context`: the retrieved context from RAG (if any)
    - `history`: the recent conversation history
    - `agent_scratchpad`: where the *Agent* can concatenate tools use and multiple calls to the LLM.
    """
    return variables


@hook(priority=0)
def agent_prompt_suffix(prompt_suffix: str, cat) -> str:
    """Hook the main prompt suffix.

    Allows to edit the suffix of the *Main Prompt* that the Cat feeds to the *Agent*.

    The suffix is concatenated to `agent_prompt_prefix` when RAG context is used.

    Args:
        prompt_suffix: str
            The suffix string to be concatenated to the *Main Prompt* (prefix
        cat: StrayCat
            Stray Cat instance.

    Returns:
        prompt_suffix: str
            The suffix string to be concatenated to the *Main Prompt* (prefix).

    Notes
    -----
    The default suffix has a few placeholders:
    - {episodic_memory} provides memories retrieved from *episodic* memory (past conversations)
    - {declarative_memory} provides memories retrieved from *declarative* memory (uploaded documents)
    - {chat_history} provides the *Agent* the recent conversation history
    - {input} provides the last user's input
    - {agent_scratchpad} is where the *Agent* can concatenate tools use and multiple calls to the LLM.
    """
    return prompt_suffix
