from langchain.callbacks.base import BaseCallbackHandler

from cat.env import get_env_bool


class NewTokenHandler(BaseCallbackHandler):
    def __init__(self, stray: "StrayCat"):
        """
        Args:
            stray: StrayCat instance
        """
        self.stray = stray

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        await self.stray.send_ws_message(token, msg_type="chat_token")


class LoggingCallbackHandler(BaseCallbackHandler):
    def colored_text(self, text: str, color: str):
        """Get colored text.

        Args:
            text: The text to color.
            color: The color to use.

        Returns:
            The colored text. Supports blue, yellow, pink, green and red
        """
        colors = {
            "blue": "36;1",
            "yellow": "33;1",
            "pink": "38;5;200",
            "green": "32;1",
            "red": "31;1",
        }

        color_str = colors[color]
        return f"\u001b[{color_str}m\033[1;3m{text}\u001b[0m"

    def on_chat_model_start(self, serialized, messages, **kwargs):
        if get_env_bool("CCAT_DEBUG"):
            lc_prompt = messages[0] if isinstance(messages, list) else messages
            print(self.colored_text("\n============== LLM INPUT ===============", "green"))
            for m in lc_prompt:
                print(m if isinstance(m, str) else m.model_dump())
            print(self.colored_text("========================================", "green"))

    def on_llm_end(self, response, **kwargs):
        """Log LLM final response."""
        if get_env_bool("CCAT_DEBUG"):
            print(self.colored_text("\n============== LLM OUTPUT ===============", "blue"))
            print(response)
            print(self.colored_text("========================================", "blue"))
