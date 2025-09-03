from typing import List, Any, Literal
from typing_extensions import deprecated
from pydantic import Field

from cheshirecat.db.cruds import history as crud_history
from cheshirecat.memory.messages import BaseMessage, CatMessage, UserMessage, ConversationHistoryItem, MessageWhy
from cheshirecat.memory.utils import DocumentRecall
from cheshirecat.utils import BaseModelDict


class WorkingMemory(BaseModelDict):
    """
    Represents the volatile memory of a cat, functioning similarly to a dictionary to store temporary custom data.

    Attributes
    ----------
    agent_id: str
        The identifier of the agent
    user_id: str
        The identifier of the user
    history: List[ConversationMessage]
        A list that maintains the conversation history between the Human and the AI.
    user_message: Optional[UserMessage], default=None
        An optional UserMessage object representing the last user message.
    recall_query: str, default=""
        A string that stores the last recall query.
    declarative_memories: List
        A list for storing declarative memories.
    procedural_memories: List
        A list for storing procedural memories.
    model_interactions: List
        A list of interactions with models.
    """
    agent_id: str
    user_id: str

    # stores conversation history
    history: List[ConversationHistoryItem] | None = Field(default_factory=list)
    user_message: UserMessage | None = None

    # recalled memories attributes
    recall_query: str = ""

    declarative_memories: List[DocumentRecall] = Field(default_factory=list)
    procedural_memories: List[DocumentRecall] = Field(default_factory=list)

    # track models usage
    model_interactions: List = Field(default_factory=list)

    def __init__(self, **data: Any):
        super().__init__(**data)

        self.history = [
            ConversationHistoryItem(**info) for info in crud_history.get_history(self.agent_id, self.user_id)
        ]

    def set_history(self, conversation_history: List[ConversationHistoryItem]) -> "WorkingMemory":
        """
        Set the conversation history.

        Args:
            conversation_history: The conversation history to save

        Returns:
            The current instance of the WorkingMemory class.
        """
        crud_history.set_history(self.agent_id, self.user_id, conversation_history)
        self.history = conversation_history

        return self

    def reset_history(self) -> "WorkingMemory":
        """
        Reset the conversation history.

        Returns:
            The current instance of the WorkingMemory class.
        """
        crud_history.set_history(self.agent_id, self.user_id, [])
        self.history = []

        return self

    @deprecated("use `update_history` instead.")
    def update_conversation_history(
        self,
        who: Literal["user", "assistant"],
        message: str,
        image: str | None = None,
        why: MessageWhy | None = None,
    ):
        """
        Update the conversation history.

        The methods append to the history key the last three conversation turns.

        Args
            who: str
                Who said the message. Can either be Role.Human or Role.AI.
            message: str
                The message said.
            image: (Optional[str], default=None): image file URL or base64 data URI that represent image associated with
                the message.
            why: MessageWhy, optional
                The reason why the message was said. Default is None.
        """
        message = CatMessage(text=message, why=why) if who == "assistant" else UserMessage(text=message, image=image)

        return self.update_history(who, message)

    def update_history(self, who: Literal["user", "assistant"], content: BaseMessage):
        """
        Update the conversation history.

        Args
            who: str, who said the message. Can either be "user" or "assistant".
            content: BaseMessage, the message said.
        """
        # we are sure that who is not change in the current call
        conversation_history_item = ConversationHistoryItem(who=who, content=content)

        # append the latest message in conversation
        self.history = [
            ConversationHistoryItem(**info)
            for info in crud_history.update_history(self.agent_id, self.user_id, conversation_history_item)
        ]

    def pop_last_message_if_human(self) -> None:
        """
        Pop the last message if it was said by the human.
        """
        if not self.history or self.history[-1].who != "user":
            return

        self.history.pop()
        crud_history.set_history(self.agent_id, self.user_id, self.history)

    @property
    def user_message_json(self) -> UserMessage | None:
        return self.user_message
