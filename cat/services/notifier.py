from typing import Any, Literal, Final, get_args

from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.auth.permissions import AuthUserInfo
from cat.log import log
from cat.services.memory.messages import CatMessage

MSG_TYPES = Literal["notification", "chat", "error", "chat_token"]


class NotifierService:
    def __init__(self, user: AuthUserInfo, agent_key: str, chat_id: str):
        self.user: Final[AuthUserInfo] = user
        self.agent_key: Final[str] = agent_key
        self.chat_id: Final[str] = chat_id

    async def _send_ws_json(self, data: Any):
        ws_connection = BillTheLizard().websocket_manager.get_connection(self.user.id)
        if not ws_connection:
            log.debug(f"No websocket connection is open for user {self.user.id}")
            return

        try:
            await ws_connection.send_json(data)
        except RuntimeError as e:
            log.error(f"Runtime error occurred while sending data: {e}")

    async def send_ws_message(self, content: str, msg_type: MSG_TYPES = "notification"):
        """
        Send a message via websocket.

        This method is useful for sending a message via websocket directly without passing through the LLM.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            content (str): The content of the message.
            msg_type (str): The type of the message. Should be either `notification` (default), `chat`, `chat_token` or `error`

        Examples
        --------
        Send a notification via websocket
        >> cat.send_ws_message("Hello, I'm a notification!")
        Send a chat message via websocket
        >> cat.send_ws_message("Meooow!", msg_type="chat")

        Send an error message via websocket
        >> cat.send_ws_message("Something went wrong", msg_type="error")
        Send custom data
        >> cat.send_ws_message({"What day it is?": "It's my unbirthday"})
        """
        options = get_args(MSG_TYPES)

        if msg_type not in options:
            raise ValueError(
                f"The message type `{msg_type}` is not valid. Valid types: {', '.join(options)}"
            )

        if msg_type == "error":
            await self._send_ws_json(
                {"type": msg_type, "name": "GenericError", "description": str(content)}
            )
            return
        await self._send_ws_json({"type": msg_type, "content": content})

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

        await self._send_ws_json(response.model_dump())

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
        await self.send_ws_message(content=content, msg_type="notification")

    async def send_error(self, error: str | Exception):
        """
        Sends an error message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            error (Union[str, Exception]): message to send

        Examples
        --------
        Send an error message to the user
        >> cat.send_error("Something went wrong!")
        or
        >> cat.send_error(CustomException("Something went wrong!"))
        """
        error_message = {
            "type": "error",
            "name": "GenericError",
            "description": error,
        } if isinstance(error, str) else {
            "type": "error",
            "name": error.__class__.__name__,
            "description": str(error),
        }

        await self._send_ws_json(error_message)
