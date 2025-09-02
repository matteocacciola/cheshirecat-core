from typing import Dict

from cheshirecat.mad_hatter.decorators import hook
from cheshirecat.memory.messages import MessageWhy
from cheshirecat.memory.utils import VectorMemoryCollectionTypes


@hook(priority=1)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
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

    return message
