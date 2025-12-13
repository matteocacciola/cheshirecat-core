from langchain_core.messages import AIMessage, HumanMessage

from cat.db.models import generate_uuid
from cat.memory.messages import UserMessage, CatMessage, ConversationMessage
from cat.memory.working_memory import WorkingMemory

from tests.utils import agent_id, chat_id


def create_working_memory_with_convo_history():
    """Utility to create a working memory and populate its convo history."""
    working_memory = WorkingMemory(agent_id=agent_id, user_id=generate_uuid(), chat_id=chat_id)
    human_message = UserMessage(text="Hi")
    working_memory.update_history(who="user", content=human_message)
    cat_message = CatMessage(text="Meow")
    working_memory.update_history(who="assistant", content=cat_message)
    return working_memory


def test_create_working_memory():
    wm = WorkingMemory(agent_id=agent_id, user_id=generate_uuid(), chat_id=chat_id)
    assert wm.history == []
    assert wm.user_message_json is None
    assert wm.recall_query == ""
    assert wm.declarative_memories == []
    assert wm.model_interactions == []


def test_update_history():
    wm = create_working_memory_with_convo_history()

    assert len(wm.history) == 2
    for message in wm.history:
        assert isinstance(message, ConversationMessage)
        assert isinstance(message.content, (UserMessage, CatMessage))

    assert wm.history[0].who == "user"
    assert wm.history[0].role == "user"
    assert wm.history[0].content.text == "Hi"

    assert wm.history[1].who == "assistant"
    assert wm.history[1].role == "assistant"
    assert wm.history[1].content.text == "Meow"


def test_langchainfy_chat_history():
    wm = create_working_memory_with_convo_history()
    langchain_convo = [h.langchainfy() for h in wm.history[-5:]]

    assert len(langchain_convo) == len(wm.history)

    assert isinstance(langchain_convo[0], HumanMessage)
    assert langchain_convo[0].name == "user"
    assert isinstance(langchain_convo[0].content, list)
    assert langchain_convo[0].content[0] == {"type": "text", "text": "Hi"}

    assert isinstance(langchain_convo[1], AIMessage)
    assert langchain_convo[1].name == "assistant"
    assert langchain_convo[1].content == "Meow"


def test_working_memory_as_dictionary_object():
    wm = WorkingMemory(agent_id=agent_id, user_id=generate_uuid(), chat_id=chat_id)
    wm.a = "a"
    wm["b"] = "b"
    assert wm.a == "a"
    assert wm["a"] == "a"
    assert wm.b == "b"
    assert wm["b"] == "b"
