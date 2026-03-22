import json
from typing import Literal, Final, get_args

from cat.auth.permissions import AuthUserInfo
from cat.log import log
from cat.services.memory.messages import CatMessage

MSG_TYPES = Literal["notification", "chat", "error", "chat_token", "memory_recall", "tool", "thought", "llm_thinking"]


class NotifierService:
    def __init__(self, user: AuthUserInfo, agent_key: str, chat_id: str):
        self.user: Final[AuthUserInfo] = user
        self.agent_key: Final[str] = agent_key
        self.chat_id: Final[str] = chat_id

    def has_ws_connection(self) -> bool:
        from cat.looking_glass.bill_the_lizard import BillTheLizard

        return BillTheLizard().websocket_manager.get_connection(self.chat_id) is not None

    async def _send_ws_message(self, content: str, msg_type: MSG_TYPES):
        """
        Send a message via websocket.

        This method is useful for sending a message via websocket directly without passing through the LLM.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            content (str): The content of the message.
            msg_type (str): The type of the message. Should be either `notification` (default), `chat`, `chat_token` or `error`
        """
        from cat.looking_glass.bill_the_lizard import BillTheLizard

        options = get_args(MSG_TYPES)
        if msg_type not in options:
            raise ValueError(
                f"The message type `{msg_type}` is not valid. Valid types: {', '.join(options)}"
            )

        ws_connection = BillTheLizard().websocket_manager.get_connection(self.chat_id)
        if not ws_connection:
            log.debug(f"No websocket connection is open for conversation {self.chat_id}. Skipping sending message: {content}")
            return

        try:
            await ws_connection.send_json({"type": msg_type, "content": content})
        except RuntimeError as e:
            log.error(f"Runtime error occurred while sending data: {e}")

    async def send_chat_token(self, chat_token: str):
        """
        Sends a chat token through a WebSocket connection.

        This asynchronous method sends the provided chat token to a WebSocket connection using the specified message
        type.

        Args:
            chat_token (str): The chat token to be sent.
        """
        await self._send_ws_message(chat_token, msg_type="chat_token")

    async def send_chat_message(self, message: str | CatMessage):
        """
        Sends a chat message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged

        Args:
            message (str | CatMessage): message to send

        Examples
        --------
        Send a chat message during conversation from a hook, tool or form
        >> cat.send_chat_message("Hello, dear!")
        Using a `CatMessage` object
        >> message = CatMessage(text="Hello, dear!", user_id=cat.user.id)
        ... cat.send_chat_message(message)
        """
        from cat.looking_glass import ChatResponse

        if isinstance(message, str):
            message = CatMessage(text=message)

        response = ChatResponse(
            agent_id=self.agent_key,
            user_id=self.user.id,
            chat_id=self.chat_id,
            message=message,
        )

        await self._send_ws_message(json.dumps(response.model_dump()), msg_type="chat")

    async def send_notification(self, content: str):
        """
        Sends a notification message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            content (str): message to send

        Examples
        --------
        Send a notification to the user
        >> cat.send_notification("It's late!")
        """
        await self._send_ws_message(content=content, msg_type="notification")

    async def send_error(self, error: str | Exception):
        """
        Sends an error message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            error (str | Exception): message to send

        Examples
        --------
        Send an error message to the user
        >> cat.send_error("Something went wrong!")
        or
        >> cat.send_error(CustomException("Something went wrong!"))
        """
        await self._send_ws_message(str(error), msg_type="error")

    async def send_context(self, content: str):
        """
        Sends a context message to the user using the active WebSocket connection.

        Args:
            content (str): message to send to the user via websocket

        Examples
        --------
        Send a debug message to the user
        >> cat.send_debug("This is a debug message!")
        """
        await self._send_ws_message(content, msg_type="memory_recall")

    async def send_tool_message(self, content: str):
        """
        Sends a tool message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            content (str): message to send to the user via websocket

        Examples
        --------
        Send a tool message to the user
        >> cat.send_tool_message("I'm using a tool!")
        """
        await self._send_ws_message(content, msg_type="tool")

    async def send_thought_message(self, content: str):
        """
        Sends a thought message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            content (str): message to send to the user via websocket

        Examples
        --------
        Send a thought message to the user
        >> cat.send_thinking_message("I'm thinking...")
        """
        await self._send_ws_message(content, msg_type="thought")

    async def send_llm_thinking(self, content: str):
        """
        Sends an LLM thinking/reasoning step to the user using the active WebSocket connection.
        Used to surface internal reasoning from models that support extended thinking
        (e.g. Anthropic Claude extended thinking, DeepSeek R1 <think> tags, OpenAI o-series reasoning).

        Args:
            content (str): JSON-serialised ThinkingMessage to send to the user via websocket

        Examples
        --------
        Send an LLM thinking step to the user
        >> cat.send_llm_thinking('{"content": "I should check the docs...", "step": 1}')
        """
        await self._send_ws_message(content, msg_type="llm_thinking")


def get_notifier(user: AuthUserInfo, agent_key: str, chat_id: str) -> NotifierService:
    return NotifierService(user, agent_key, chat_id)
