from typing import Dict

from cat.mad_hatter.decorators import hook
from cat.memory.messages import MessageWhy


@hook(priority=1)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
    memory = {"declarative": [
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
