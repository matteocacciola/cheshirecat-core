from langchain.callbacks.base import BaseCallbackHandler


class NewTokenHandler(BaseCallbackHandler):
    def __init__(self, stray: "StrayCat"):
        """
        Args:
            stray: StrayCat instance
        """
        self.stray = stray

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        await self.stray.send_ws_message(token, msg_type="chat_token")
