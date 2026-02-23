from datetime import datetime, timezone
from typing import List, Any, Literal, Dict, Set
from pydantic import Field, field_validator

from cat.db.cruds import conversations as crud_conversations
from cat.services.memory.interactions import ModelInteraction
from cat.services.memory.messages import BaseMessage, UserMessage, ConversationMessage
from cat.services.memory.models import DocumentRecall
from cat.utils import BaseModelDict


class WorkingMemory(BaseModelDict):
    """
    Represents the volatile memory of a cat, functioning similarly to a dictionary to store temporary custom data.

    Attributes
    ----------
    agent_id: str
        The identifier of the agent
    user_id: str
        The identifier of the user
    chat_id: str
        The identifier of the chat session
    history: List[ConversationMessage]
        A list that maintains the conversation history between the Human and the AI.
    user_message: Optional[UserMessage], default=None
        An optional UserMessage object representing the last user message.
    context_memories: List
        A list for storing declarative memories.
    model_interactions: List
        A list of interactions with models.
    """
    agent_id: str
    user_id: str
    chat_id: str

    # stores conversation history
    history: List[ConversationMessage] | None = Field(default_factory=list)
    user_message: UserMessage | None = None

    context_memories: List[DocumentRecall] = Field(default_factory=list)

    # track models usage
    model_interactions: Set[ModelInteraction] = Field(default_factory=set)

    @field_validator("model_interactions")
    @classmethod
    def validate_model_interactions(cls, v):
        for item in v:
            if not isinstance(item, ModelInteraction):
                raise ValueError("model_interactions must be a list of ModelInteraction")
        return v

    def __init__(self, **data: Any):
        super().__init__(**data)

        self.history = [
            ConversationMessage(**info)
            for info in crud_conversations.get_messages(self.agent_id, self.user_id, self.chat_id)
        ]

    def reset_history(self) -> "WorkingMemory":
        """
        Reset the conversation history.

        Returns:
            The current instance of the WorkingMemory class.
        """
        crud_conversations.set_messages(self.agent_id, self.user_id, self.chat_id, [])
        self.history = []

        return self

    def update_history(self, who: Literal["user", "assistant"], content: BaseMessage) -> "WorkingMemory":
        """
        Update the conversation history.

        Args
            who: str, who said the message. Can either be "user" or "assistant".
            content: BaseMessage, the message said.
        """
        # we are sure that who is not change in the current call
        conversation_history_item = ConversationMessage(
            who=who, content=content, when=datetime.now(timezone.utc).timestamp()
        )

        # append the latest message in conversation
        self.history = [
            ConversationMessage(**info)
            for info in crud_conversations.update_messages(
                self.agent_id, self.user_id, self.chat_id, conversation_history_item
            )
        ]
        return self

    def pop_last_message_if_human(self) -> "WorkingMemory":
        """
        Pop the last message if it was said by the human.
        """
        if self.history and self.history[-1].who == "user":
            self.history.pop()
            crud_conversations.set_messages(self.agent_id, self.user_id, self.chat_id, self.history)

        return self

    @property
    def user_message_json(self) -> Dict | None:
        return self.user_message.model_dump() if self.user_message else None
