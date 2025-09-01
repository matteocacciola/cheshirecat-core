import pytest
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from cheshirecat.core_plugin.utils.memory import recall
from cheshirecat.looking_glass import StrayCat
from cheshirecat.memory.messages import CatMessage, UserMessage, MessageWhy
from cheshirecat.memory.working_memory import WorkingMemory

from tests.utils import api_key, create_mock_plugin_zip, send_file


def test_stray_initialization(stray_no_memory):
    assert isinstance(stray_no_memory, StrayCat)
    assert stray_no_memory.user.id == "user_alice"
    assert isinstance(stray_no_memory.working_memory, WorkingMemory)


def test_stray_nlp(stray_no_memory):
    res = stray_no_memory.llm(
        ChatPromptTemplate.from_messages([
            HumanMessagePromptTemplate.from_template(template="hey")
        ])
    )
    assert "You did not configure" in res

    embedding = stray_no_memory.embedder.embed_documents(["hey"])
    assert isinstance(embedding[0], list)
    assert isinstance(embedding[0][0], float)


@pytest.mark.asyncio
async def test_stray_call(stray_no_memory):
    msg = {"text": "Where do I go?"}

    reply = await stray_no_memory(UserMessage(**msg))

    assert isinstance(reply, CatMessage)
    assert "You did not configure" in reply.text
    assert reply.type == "chat"
    assert isinstance(reply.why, MessageWhy)


def test_stray_classify(stray_no_memory):
    label = stray_no_memory.classify("I feel good", labels=["positive", "negative"])
    assert label is None

    label = stray_no_memory.classify("I feel bad", labels={"positive": ["I'm happy"], "negative": ["I'm sad"]})
    assert label is None


@pytest.mark.asyncio
async def test_stray_recall_invalid_collection_name(stray, lizard):
    with pytest.raises(ValueError) as exc_info:
        await recall(stray, lizard.embedder.embed_query("Hello, I'm Alice"), "invalid_collection")
    assert "invalid_collection is not a valid collection" in str(exc_info.value)


@pytest.mark.asyncio
async def test_stray_recall_all_memories(secure_client, secure_client_headers, stray, lizard):
    expected_chunks = 4
    send_file("sample.pdf", "application/pdf", secure_client, secure_client_headers)

    query = lizard.embedder.embed_query("")
    memories = await recall(stray, query, "declarative", k=None)

    assert len(memories) == expected_chunks
    for mem in memories:
        assert mem.score is None
        assert isinstance(mem.vector, list)


@pytest.mark.asyncio
async def test_stray_recall_by_metadata(secure_client, secure_client_headers, stray, lizard):
    expected_chunks = 4
    content_type = "application/pdf"
    query = lizard.embedder.embed_query("late")

    file_name = "sample.pdf"
    _, file_path = send_file(file_name, content_type, secure_client, secure_client_headers)

    memories = await recall(stray, query, "declarative", metadata={"source": file_name})
    assert len(memories) == expected_chunks
    for mem in memories:
        assert mem.document.metadata["source"] == file_name

    with open(file_path, "rb") as f:
        files = {"file": ("sample2.pdf", f, content_type)}
        _ = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    memories = await recall(stray, query, "declarative", metadata={"source": file_name})
    assert len(memories) == expected_chunks
    for mem in memories:
        assert mem.document.metadata["source"] == file_name


@pytest.mark.asyncio
async def test_stray_fast_reply_hook(secure_client, secure_client_headers, stray):
    ccat = stray.cheshire_cat
    ccat_headers = {"agent_id": ccat.id, "Authorization": f"Bearer {api_key}"}

    # manually install the plugin
    zip_path = create_mock_plugin_zip(flat=True, plugin_id="mock_plugin_fast_reply")
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin.zip in tests/mocks folder
    with open(zip_path, "rb") as f:
        secure_client.post(
            "/admins/plugins/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=secure_client_headers
        )

    # activate for the new agent
    secure_client.put("/plugins/toggle/mock_plugin_fast_reply", headers=ccat_headers)

    msg = {"text": "hello", "user_id": stray.user.id, "agent_id": stray.agent_id}

    # send message
    res = await stray(msg)

    assert isinstance(res, CatMessage)
    assert res.text == "This is a fast reply"

    # there should be NO side effects
    assert stray.working_memory.user_message.text == "hello"
    assert len(stray.working_memory.history) == 0
