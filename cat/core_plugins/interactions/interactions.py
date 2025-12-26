from typing import List

from cat import hook, get_caller_info
from cat.core_plugins.interactions.handlers import ModelInteractionHandler


@hook(priority=1)
def llm_callbacks(callbacks: List, cat) -> List:
    caller = get_caller_info(skip=1)

    callback = ModelInteractionHandler(caller)
    callback.inject_stray(cat)
    callbacks.append(callback)

    return callbacks
