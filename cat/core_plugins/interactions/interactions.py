from typing import List

from cat.core_plugins.interactions.handlers import ModelInteractionHandler
from cat.mad_hatter.decorators import hook
from cat.utils import get_caller_info


@hook(priority=1)
def llm_callbacks(callbacks: List, cat) -> List:
    caller = get_caller_info(skip=1)
    callbacks.append(ModelInteractionHandler(cat, caller))

    return callbacks
