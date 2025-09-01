from typing import Dict

from cheshirecat.mad_hatter.decorators import hook


@hook(priority=10)
def fast_reply(reply: str | None, cat) -> str | None:
    user_msg = "hello"
    if user_msg in cat.working_memory.user_message.text:
        return "This is a fast reply"

    return reply
