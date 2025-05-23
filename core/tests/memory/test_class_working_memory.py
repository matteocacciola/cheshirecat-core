from langchain_core.messages import AIMessage, HumanMessage

from cat.convo.messages import Role, UserMessage, CatMessage, ConversationHistoryItem
from cat.db.models import generate_uuid
from cat.memory.working_memory import WorkingMemory

from tests.utils import agent_id


def create_working_memory_with_convo_history():
    """Utility to create a working memory and populate its convo history."""

    working_memory = WorkingMemory(agent_id=agent_id, user_id=generate_uuid())
    human_message = UserMessage(text="Hi")
    working_memory.update_history(who=Role.HUMAN, content=human_message)
    cat_message = CatMessage(text="Meow")
    working_memory.update_history(who=Role.AI, content=cat_message)
    return working_memory


def test_create_working_memory():
    wm = WorkingMemory(agent_id=agent_id, user_id=generate_uuid())
    assert wm.history == []
    assert wm.user_message_json is None
    assert wm.active_form is None
    assert wm.recall_query == ""
    assert wm.episodic_memories == []
    assert wm.declarative_memories == []
    assert wm.procedural_memories == []
    assert wm.model_interactions == []


def test_update_history():
    wm = create_working_memory_with_convo_history()

    assert len(wm.history) == 2
    for message in wm.history:
        assert isinstance(message, ConversationHistoryItem)
        assert isinstance(message.content, (UserMessage, CatMessage))

    assert wm.history[0].who == Role.HUMAN
    assert wm.history[0].role == "Human"
    assert wm.history[0].content.text == "Hi"

    assert wm.history[1].who == Role.AI
    assert wm.history[1].role == "AI"
    assert wm.history[1].content.text == "Meow"


def test_stringify_chat_history():
    wm = create_working_memory_with_convo_history()
    assert wm.stringify_chat_history() == "\n - Human: Hi\n - AI: Meow"


def test_langchainfy_chat_history():
    wm = create_working_memory_with_convo_history()
    langchain_convo = wm.langchainfy_chat_history()

    assert len(langchain_convo) == len(wm.history)

    assert isinstance(langchain_convo[0], HumanMessage)
    assert langchain_convo[0].name == "Human"
    assert isinstance(langchain_convo[0].content, list)
    assert langchain_convo[0].content[0] == {"type": "text", "text": "Hi"}

    assert isinstance(langchain_convo[1], AIMessage)
    assert langchain_convo[1].name == "AI"
    assert langchain_convo[1].content == "Meow"


def test_working_memory_as_dictionary_object():
    wm = WorkingMemory(agent_id=agent_id, user_id=generate_uuid())
    wm.a = "a"
    wm["b"] = "b"
    assert wm.a == "a"
    assert wm["a"] == "a"
    assert wm.b == "b"
    assert wm["b"] == "b"

# TODO V2: add tests for multimodal messages!
