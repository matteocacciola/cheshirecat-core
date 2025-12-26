import pytest
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from cat.agent import run_agent
from cat.db.cruds import users as crud_users
from cat.looking_glass import StrayCat
from cat.services.memory.messages import MessageWhy
from cat.services.memory.utils import recall, VectorMemoryType
from cat.services.memory.working_memory import WorkingMemory

from tests.utils import api_key, create_mock_plugin_zip, send_file, http_message


def test_stray_initialization(stray_no_memory):
    assert isinstance(stray_no_memory, StrayCat)
    # check that stray_no_memory.user.id is uuid4
    assert len(stray_no_memory.user.id) == 36
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
async def test_stray_call(secure_client, stray_no_memory):
    crud_users.create_user(
        stray_no_memory.agent_key,
        {
            "id": stray_no_memory.user.id,
            "username": stray_no_memory.user.name,
            "password": "password123",
            "permissions": stray_no_memory.user.permissions
        },
    )

    ccat_headers = {
        "X-Agent-ID": stray_no_memory.agent_key,
        "Authorization": f"Bearer {api_key}",
        "X-Chat-ID": stray_no_memory.id,
        "X-User-ID": stray_no_memory.user.id,
    }

    # send message
    status_code, response_json = http_message(secure_client,{"text": "Where do I go?"}, ccat_headers)

    assert status_code == 200
    assert response_json["agent_id"] == stray_no_memory.agent_key
    assert response_json["user_id"] == stray_no_memory.user.id
    assert response_json["chat_id"] == stray_no_memory.id
    assert response_json["message"]["type"] == "chat"
    assert "You did not configure" in response_json["message"]["text"]
    assert "You did not configure" in response_json["message"]["content"]

    assert response_json["message"]["why"]["input"] == "Where do I go?"
    assert response_json["message"]["why"]["intermediate_steps"] == []
    assert response_json["message"]["why"]["memory"] == {'declarative': []}

    why = MessageWhy(**response_json["message"]["why"])
    assert isinstance(why, MessageWhy)


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
    crud_users.create_user(
        stray.agent_key,
        {
            "id": stray.user.id,
            "username": stray.user.name,
            "password": "password123",
            "permissions": stray.user.permissions
        },
    )

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

    # send message
    status_code, response_json = http_message(
        secure_client, {"text": "hello"}, ccat_headers | {"X-Chat-ID": stray.id, "X-User-ID": stray.user.id},
    )
    assert status_code == 200
    assert response_json["agent_id"] == stray.agent_key
    assert response_json["user_id"] == stray.user.id
    assert response_json["chat_id"] == stray.id
    assert response_json["message"]["type"] == "chat"
    assert response_json["message"]["text"] == "This is a fast reply"
    assert response_json["message"]["content"] == "This is a fast reply"

    # there should be NO side effects
    upd_stray = StrayCat(
        user_data=stray.user,
        agent_id=stray.agent_key,
        stray_id=stray.id,
        plugin_manager_generator=lambda: stray.plugin_manager,
    )
    assert len(upd_stray.working_memory.history) == 0
