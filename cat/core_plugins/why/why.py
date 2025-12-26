from typing import Dict

from cat import hook, MessageWhy
from cat.services.memory.utils import VectorMemoryType


@hook(priority=1)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
    memory = {str(VectorMemoryType.DECLARATIVE): [
        dict(d.document)
        | {
            "score": float(d.score) if d.score else None,
            "id": d.id,
        }
        for d in cat.working_memory.declarative_memories
    ]}

    # why this response?
    message.why = MessageWhy(
        input=cat.working_memory.user_message.text,
        intermediate_steps=agent_output.intermediate_steps,
        memory=memory,
    )

    return message
