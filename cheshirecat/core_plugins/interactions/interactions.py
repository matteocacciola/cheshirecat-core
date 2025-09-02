from typing import List

from cheshirecat.core_plugins.interactions.handlers import ModelInteractionHandler
from cheshirecat.mad_hatter.decorators import hook
from cheshirecat.utils import get_caller_info


@hook(priority=1)
def llm_callbacks(callbacks: List, cat) -> List:
    caller = get_caller_info(skip=1)
    callbacks.append(ModelInteractionHandler(cat, caller))

    return callbacks
