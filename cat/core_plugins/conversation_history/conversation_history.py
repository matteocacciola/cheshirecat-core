from typing import Dict

from cat.mad_hatter.decorators import hook
from cat.memory.messages import UserMessage


@hook(priority=2)
def before_cat_reads_message(user_message: UserMessage, cat) -> UserMessage:
    # update conversation history (user turn)
    cat.working_memory.update_history(who="user", content=user_message)

    return user_message


@hook(priority=1)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
    if agent_output.with_llm_error:
        cat.working_memory.pop_last_message_if_human()
    else:
        # update conversation history (AI turn)
        cat.working_memory.update_history(who="assistant", content=message)

    return message
