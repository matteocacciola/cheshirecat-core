from typing import List, Any
from typing_extensions import deprecated
from pydantic import Field

from cat.agents import AgentInput
from cat.convo.messages import (
    Role,
    BaseMessage,
    CatMessage,
    UserMessage,
    MessageWhy,
    ConversationHistoryItem,
    ConversationHistory,
    convert_to_conversation_history,
    convert_to_langchain_message,
)
from cat.convo.model_interactions import LLMModelInteraction, EmbedderModelInteraction
from cat.db.cruds import history as crud_history
from cat.experimental.form.cat_form import CatForm
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.memory.utils import DocumentRecall
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
    history: List[ConversationMessage]
        A list that maintains the conversation history between the Human and the AI.
    user_message: Optional[UserMessage], default=None
        An optional UserMessage object representing the last user message.
    active_form: Optional[CatForm], default=None
        An optional reference to a CatForm currently in use.
    recall_query: str, default=""
        A string that stores the last recall query.
    episodic_memories: List
        A list for storing episodic memories.
    declarative_memories: List
        A list for storing declarative memories.
    procedural_memories: List
        A list for storing procedural memories.
    model_interactions: List[ModelInteraction]
        A list of interactions with models.
    """

    agent_id: str
    user_id: str

    # stores conversation history
    history: ConversationHistory | None = Field(default_factory=list)
    user_message: UserMessage | None = None
    active_form: CatForm | None = None

    # recalled memories attributes
    recall_query: str = ""
    episodic_memories: List[DocumentRecall] = Field(default_factory=list)
    declarative_memories: List[DocumentRecall] = Field(default_factory=list)
    procedural_memories: List[DocumentRecall] = Field(default_factory=list)

    # track models usage
    model_interactions: List[LLMModelInteraction | EmbedderModelInteraction] = Field(default_factory=list)

    def __init__(self, **data: Any):
        super().__init__(**data)

        self.history = convert_to_conversation_history(crud_history.get_history(self.agent_id, self.user_id))

    def set_history(self, conversation_history: ConversationHistory) -> "WorkingMemory":
        """
        Set the conversation history.

        Args:
            conversation_history: The conversation history to save

        Returns:
            The current instance of the WorkingMemory class.
        """

        crud_history.set_history(
            self.agent_id, self.user_id, [message.model_dump() for message in conversation_history]
        )
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
        who: Role,
        message: str,
        image: str | None = None,
        audio: str | None = None,
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
            audio: (Optional[str], default=None): audio file URL or base64 data URI that represent audio associated with
                the message.
            why: MessageWhy, optional
                The reason why the message was said. Default is None.
        """

        message = CatMessage(text=message, image=image, audio=audio, why=why) if who == Role.AI else UserMessage(
            text=message, image=image, audio=audio,
        )

        return self.update_history(who, message)

    def update_history(self, who: Role, content: BaseMessage):
        """
        Update the conversation history.

        Args
            who: Role, who said the message. Can either be Role.Human or Role.AI.
            content: BaseMessage, the message said.
        """

        # we are sure that who is not change in the current call
        conversation_history_item = ConversationHistoryItem(who=who, content=content)

        # append latest message in conversation
        self.history = convert_to_conversation_history(
            crud_history.update_history(self.agent_id, self.user_id, conversation_history_item)
        )

    def pop_last_message_if_human(self) -> None:
        """
        Pop the last message if it was said by the human.
        """

        if not self.history or self.history[-1].who != Role.HUMAN:
            return

        self.history.pop()
        crud_history.set_history(
            self.agent_id, self.user_id, [message.model_dump() for message in self.history]
        )

    def stringify_chat_history(self, latest_n: int = 10) -> str:
        """
        Serialize chat history.
        Converts to text the recent conversation turns.
        Useful for backward compatibility with old non-chat models, and to easily insert convo into a prompt without
        using dedicated objects and libraries.

        Args:
            latest_n (int. optional): How many latest turns to stringify. Defaults to 5.

        Returns:
            str: String with recent conversation turns.

        Notes
        -----
        Such context is placed in the `agent_prompt_suffix` in the place held by {chat_history}.

        The chat history is a dictionary with keys::
            'who': the name of who said the utterance;
            'message': the utterance.
        """

        history = self.history[-latest_n:]
        history = [h.model_dump() for h in history]

        history_strings = [f"\n - {str(turn['who'])}: {turn['message']}" for turn in history]
        return "".join(history_strings)

    def langchainfy_chat_history(self, latest_n: int = 5) -> List[BaseMessage]:
        """
        Convert chat history in working memory to Langchain objects.

        Args:
            latest_n (int, optional): Number of latest messages to get. Defaults to 5.

        Returns:
            List[BaseMessage]: List of Langchain messages.
        """

        chat_history = self.history[-latest_n:]

        return [convert_to_langchain_message(h) for h in chat_history]

    @property
    def user_message_json(self) -> UserMessage | None:
        return self.user_message

    @property
    def lizard(self) -> BillTheLizard:
        return BillTheLizard()

    @property
    def cheshire_cat(self) -> CheshireCat:
        ccat = self.lizard.get_cheshire_cat(self.agent_id)
        if not ccat:
            raise ValueError(f"Cheshire Cat not found for the StrayCat {self.__user.id}.")

        return ccat
