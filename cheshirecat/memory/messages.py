import time
from abc import ABC
from typing import Literal, List, Dict
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage as BaseLangChainMessage
from pydantic import computed_field
from typing_extensions import deprecated

from cheshirecat.utils import BaseModelDict


class MessageWhy(BaseModelDict):
    """
    Class for wrapping message why. This is used to explain why the agent replied with the message.

    Variables:
        input (str): input message
        intermediate_steps (List): intermediate steps
        memory (Dict): memory
    """
    input: str
    intermediate_steps: List
    memory: Dict


class BaseMessage(BaseModelDict, ABC):
    """
    Class for wrapping cat or human message.

    Variables:
        text (str): message
    """
    text: str


class CatMessage(BaseMessage):
    """
    Class for wrapping cat message. This is used to send the message to the cat. It is based on the BaseMessage class.

    Variables:
        text (str): cat message
        why (MessageWhy): why the agent replied with the message
        error (Optional[str], default=None): error message if any error occurred while generating the message
    """
    why: MessageWhy | None = None
    error: str | None = None

    @computed_field
    @property
    def type(self) -> str:
        return "chat"

    @computed_field
    @property
    @deprecated("This attribute is deprecated. Use `text` instead.")
    def content(self) -> str:
        """
        This attribute is deprecated. Use `text` instead. Get the text content of the message.

        Returns:
            str: The text content of the message.
        """
        return self.text

    @content.setter
    def content(self, value: str):
        """
        This attribute is deprecated. Use `text` instead. Set the text content of the message.

        Args:
            value: str
        """
        self.text = value


class UserMessage(BaseMessage):
    """
    Class for wrapping user message. This is used to send the message to the agent. It is based on the BaseMessage
    class.

    Variables:
        text (str): user message
        image: (Optional[str], default=None): image file URL or base64 data URI that represent image associated with
            the message.
    """
    image: str | None = None


class ConversationHistoryItem(BaseModelDict):
    """
    Class for wrapping conversation history items. This is used to store the conversation history. It can be either
    assistant or user. The conversation history is then persisted in the database.

    Variables:
        who (Role): who is the author of the message (`assistant` or `user`)
        when (float): when the message was sent in seconds since epoch (default: time.time())
        content (BaseMessage): content of the message
    """
    who: Literal["user", "assistant"]
    when: float | None = time.time()
    content: CatMessage | UserMessage

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        content_dict = self.content.model_dump()
        self.content = CatMessage(**content_dict) if self.who == "assistant" else UserMessage(**content_dict)

    def __str__(self):
        return f"\n - {str(self.who)}: {self.content.text}"

    @computed_field
    @property
    @deprecated("This attribute is deprecated. Use `content.text` instead")
    def message(self) -> str:
        """
        This attribute is deprecated. Use `content.text` instead. Get the text content of the message.

        Returns:
            str: The text content of the message.
        """
        return self.content.text

    @message.setter
    def message(self, value: str):
        """
        This attribute is deprecated. Use `content.text` instead. Set the text content of the message.

        Args:
            value: str
        """
        self.content.text = value

    @computed_field
    @property
    @deprecated("This attribute is deprecated. Use `content.why` instead")
    def why(self) -> MessageWhy | None:
        """
        This attribute is deprecated. Use `content.why` instead. Deprecated. Get additional context about the message.

        Returns:
            MessageWhy (optional): The additional context about the message, or None.
        """
        return self.content.why if isinstance(self.content, CatMessage) else None

    @why.setter
    def why(self, value: MessageWhy | None):
        """
        This attribute is deprecated. Use `content.why` instead. Set additional context about the message.

        Args:
            value: MessageWhy | None
        """
        if isinstance(self.content, CatMessage):
            self.content.why = value

    @computed_field
    @property
    @deprecated("This attribute is deprecated. Use `who` instead")
    def role(self) -> Literal["user", "assistant"]:
        """
        This attribute is deprecated. Use `who` instead. Get the name of the message author.

        Returns
            Role: The author of the speaker.
        """
        return self.who

    @role.setter
    def role(self, value: Literal["user", "assistant"]):
        """
        This attribute is deprecated. Use `who` instead. Set the name of the message author.

        Args:
            value: Role
        """
        self.who = value

    def langchainfy(self) -> BaseLangChainMessage:
        """
        Convert the internal ConversationHistoryItem to a LangChain BaseMessage.

        Returns
        -------
        BaseLangChainMessage
            The LangChain BaseMessage converted from the internal ConversationHistoryItem.
        """
        if self.who == "assistant":
            return AIMessage(name=self.who, content=self.content.text)

        content = [{"type": "text", "text": self.content.text}]
        if self.content.image:
            content.append({"type": "image_url", "image_url": {"url": self.content.image}})

        return HumanMessage(name=self.who, content=content)
