"""Hooks to modify the prompts.

Here is a collection of methods to hook the prompts components that instruct the *Agent*.

"""
from cat.mad_hatter.decorators import hook


@hook(priority=0)
def agent_system_prompt(prompt: str, cat) -> str:
    """Hook the main prompt.

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
    The default prompt describe who the AI is and how it is expected to answer the Human.
    """
    return prompt


@hook(priority=0)
def agent_prompt_instructions(instructions: str, cat) -> str:
    """Hook the instruction prompt.

    Allows to edit the instructions that the Cat feeds to the *Agent* to select tools and forms.

    Args:
        instructions: str
            Instructions prompt to select tool or form.
        cat: StrayCat
            Stray Cat instance.

    Returns:
        instructions: str
            Instructions prompt to select tool or form

    Notes
    -----
    This prompt explains the *Agent* how to select a tool or form.
    """
    return instructions
