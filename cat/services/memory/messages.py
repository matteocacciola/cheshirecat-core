from abc import ABC
from typing import Literal, List, Dict, Any
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage as BaseLangChainMessage
from pydantic import computed_field, BaseModel

from cat.utils import BaseModelDict, retrieve_image


class MessageWhy(BaseModel):
    """
    Class for wrapping message why. This is used to explain why the agent replied with the message.

    Variables:
        input (str): input message
        intermediate_steps (List): intermediate steps
        memory (List[Dict[str, Any]]): memory used to generate the message
    """
    input: str
    intermediate_steps: List
    memory: List[Dict[str, Any]]


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


class ConversationMessage(BaseModel):
    """
    Class for wrapping conversation messages. This is used to store the conversation history. It can be either
    assistant or user. The conversation history is then persisted in the database.

    Variables:
        who (str): who is the author of the message (`assistant` or `user`)
        when (float): when the message was sent in seconds since epoch (default: current timestamp in UTC)
        content (BaseMessage): content of the message
    """
    who: Literal["user", "assistant"]
    when: float
    content: CatMessage | UserMessage

    def __init__(self, **data):
        content = data.get("content")
        who = data.get("who")
        data["content"] = CatMessage(**content) if who == "assistant" else UserMessage(**content)

        super().__init__(**data)

    def langchainfy(self) -> BaseLangChainMessage:
        """
        Convert the internal ConversationHistoryItem to a LangChain BaseMessage.

        Returns:
            BaseLangChainMessage: The LangChain BaseMessage converted from the internal ConversationHistoryItem.
        """
        if self.who == "assistant":
            return AIMessage(name=self.who, content=self.content.text)

        content = [{"type": "text", "text": self.content.text}]
        if (image_formatted := retrieve_image(self.content.image)) is not None:
            content.append({"type": "image_url", "image_url": {"url": image_formatted}})
        return HumanMessage(name=self.who, content=content)
