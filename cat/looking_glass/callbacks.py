from langchain_core.callbacks import BaseCallbackHandler

from cat.env import get_env_bool
from cat.services.notifier import NotifierService
from cat.utils import colored_text


class NewTokenHandler(BaseCallbackHandler):
    def __init__(self, notifier: NotifierService):
        """
        Args:
            notifier: NotifierService instance
        """
        self.notifier = notifier

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        await self.notifier.send_ws_message(token, msg_type="chat_token")


class LoggingCallbackHandler(BaseCallbackHandler):
    def on_chat_model_start(self, serialized, messages, **kwargs):
        if get_env_bool("CCAT_DEBUG"):
            lc_prompt = messages[0] if isinstance(messages, list) else messages
            print(colored_text("\n============== LLM INPUT ===============", "green"))
            for m in lc_prompt:
                print(m if isinstance(m, str) else m.model_dump())
            print(colored_text("========================================", "green"))

    def on_llm_end(self, response, **kwargs):
        """Log LLM final response."""
        if get_env_bool("CCAT_DEBUG"):
            print(colored_text("\n============== LLM OUTPUT ===============", "blue"))
            print(response)
            print(colored_text("========================================", "blue"))
