import pytest
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from cat.agent import run_agent
from cat.looking_glass import StrayCat
from cat.services.memory.messages import CatMessage, UserMessage, MessageWhy
from cat.services.memory.utils import recall, VectorMemoryType
from cat.services.memory.working_memory import WorkingMemory

from tests.utils import api_key, create_mock_plugin_zip, send_file


def test_stray_initialization(stray_no_memory):
    assert isinstance(stray_no_memory, StrayCat)
    assert stray_no_memory.user.id == "user_alice"
    assert isinstance(stray_no_memory.working_memory, WorkingMemory)


@pytest.mark.asyncio
async def test_stray_nlp(lizard, stray_no_memory):
    res = await run_agent(
        llm=stray_no_memory.large_language_model,
        prompt=ChatPromptTemplate.from_messages([
            HumanMessagePromptTemplate.from_template(template="hey")
        ]),
    )
    assert "You did not configure" in res.output

    embedding = lizard.embedder.embed_documents(["hey"])
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


@pytest.mark.asyncio
async def test_stray_recall_all_memories(secure_client, secure_client_headers, stray, lizard):
    send_file("sample.pdf", "application/pdf", secure_client, secure_client_headers)

    query = lizard.embedder.embed_query("")
    memories = await recall(stray, query, VectorMemoryType.DECLARATIVE, k=None)

    assert len(memories) > 0
    for mem in memories:
        assert mem.score is None
        assert isinstance(mem.vector, list)


@pytest.mark.asyncio
async def test_stray_recall_by_metadata(secure_client, secure_client_headers, stray, lizard):
    content_type = "application/pdf"
    query = lizard.embedder.embed_query("late")

    file_name = "sample.pdf"
    _, file_path = send_file(file_name, content_type, secure_client, secure_client_headers)

    memories = await recall(stray, query, VectorMemoryType.DECLARATIVE, metadata={"source": file_name})
    assert len(memories) > 0
    for mem in memories:
        assert mem.document.metadata["source"] == file_name

    with open(file_path, "rb") as f:
        files = {"file": ("sample2.pdf", f, content_type)}
        _ = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)

    memories = await recall(stray, query, VectorMemoryType.DECLARATIVE, metadata={"source": file_name})
    assert len(memories) > 0
    for mem in memories:
        assert mem.document.metadata["source"] == file_name


@pytest.mark.asyncio
async def test_stray_fast_reply_hook(secure_client, secure_client_headers, stray):
    ccat_headers = {"X-Agent-ID": stray.agent_key, "Authorization": f"Bearer {api_key}"}

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

    msg = {"text": "hello", "user_id": stray.user.id, "agent_id": stray.agent_key}

    # send message
    res = await stray(msg)

    assert isinstance(res, CatMessage)
    assert res.text == "This is a fast reply"

    # there should be NO side effects
    assert stray.working_memory.user_message.text == "hello"
    assert len(stray.working_memory.history) == 0
