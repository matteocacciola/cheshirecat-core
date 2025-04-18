import time
from abc import ABC
from typing import List, Dict, TypeAlias
from langchain_core.messages import AIMessage, HumanMessage, BaseMessage as BaseLangchainMessage
from pydantic import computed_field
from typing_extensions import deprecated

from cat.convo.model_interactions import LLMModelInteraction, EmbedderModelInteraction
from cat.utils import BaseModelDict, Enum


class Role(Enum):
    """
    Enum for role of the agent in the conversation history info. It can be either AI or Human (Enum).

    Variables:
        AI (str): AI
        HUMAN (str): Human
    """
    AI = "AI"
    HUMAN = "Human"


class MessageWhy(BaseModelDict):
    """
    Class for wrapping message why. This is used to explain why the agent replied with the message.

    Variables:
        input (str): input message
        intermediate_steps (List): intermediate steps
        memory (Dict): memory
        model_interactions (List[LLMModelInteraction | EmbedderModelInteraction]): model interactions
    """

    input: str
    intermediate_steps: List
    memory: Dict
    model_interactions: List[LLMModelInteraction | EmbedderModelInteraction]


class BaseMessage(BaseModelDict, ABC):
    """
    Class for wrapping cat or human message.

    Variables:
        text (str): cat message
        image: (Optional[str], default=None): image file URL or base64 data URI that represent image associated with
            the message.
    """

    text: str
    image: str | None = None


class CatMessage(BaseMessage):
    """
    Class for wrapping cat message. This is used to send the message to the cat. It is based on the BaseMessage class.

    Variables:
        text (str): cat message
        image: (Optional[str], default=None): image file URL or base64 data URI that represent image associated with
            the message
        why (MessageWhy): why the agent replied with the message
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
    pass


class ConversationHistoryItem(BaseModelDict):
    """
    Class for wrapping conversation history items. This is used to store the conversation history. It can be either AI
    or Human. The conversation history is then persisted in the database.

    Variables:
        who (Role): who is the author of the message (AI or Human)
        when (float): when the message was sent in seconds since epoch (default: time.time())
        content (BaseMessage): content of the message
    """

    who: Role
    when: float | None = time.time()
    content: CatMessage | UserMessage

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        content_dict = self.content.model_dump()
        self.content = CatMessage(**content_dict) if self.who == Role.AI else UserMessage(**content_dict)

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
    def role(self) -> Role:
        """
        This attribute is deprecated. Use `who` instead. Get the name of the message author.

        Returns
            Role: The author of the speaker.
        """
        return self.who

    @role.setter
    def role(self, value: Role):
        """
        This attribute is deprecated. Use `who` instead. Set the name of the message author.

        Args:
            value: Role
        """
        self.who = value


ConversationHistory: TypeAlias = List[ConversationHistoryItem]


def convert_to_langchain_message(history_info: ConversationHistoryItem) -> BaseLangchainMessage:
    """
    Convert a conversation history info to a langchain message. The langchain message can be either an AI message or a
    human message.

    Args:
        history_info: ConversationHistoryInfo, the conversation history info to convert

    Returns:
        BaseLangchainMessage: The langchain message
    """

    if history_info.who == Role.AI:
        return AIMessage(name=str(history_info.who), content=history_info.content.text)

    content = [{"type": "text", "text": history_info.content.text}]
    if history_info.content.image:
        content.append({"type": "image_url", "image_url": {"url": history_info.content.image}})

    return HumanMessage(name=str(history_info.who), content=content)


def convert_to_cat_message(ai_message: AIMessage, why: MessageWhy) -> CatMessage:
    content = ai_message.content

    if isinstance(content, str):
        return CatMessage(text=content, why=why)

    image = None
    text = None
    for item in content:
        if isinstance(item, str):
            text = item
            continue

        if "type" not in item:
            continue

        match item["type"]:
            case "text":
                text = item
            case "image_url":
                image = item["image_url"]["url"]

    return CatMessage(text=text, image=image, why=why)


def convert_to_conversation_history(infos: List[Dict]) -> ConversationHistory:
    return [ConversationHistoryItem(**info) for info in infos]
