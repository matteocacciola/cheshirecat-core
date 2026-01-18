import asyncio
from json import dumps
import pytest
from fastapi.encoders import jsonable_encoder

from cat.services.memory.models import VectorMemoryType
from cat.services.service_factory import ServiceFactory

from tests.utils import send_file, api_key, chat_id


def test_get_all_embedder_settings(secure_client, secure_client_headers, lizard):
    embedder_schemas = ServiceFactory(
        agent_key=lizard.agent_key,
        hook_manager=lizard.plugin_manager,
        factory_allowed_handler_name="factory_allowed_embedders",
        setting_category="embedder",
        schema_name="languageEmbedderName",
    ).get_schemas()
    response = secure_client.get("/embedder/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(embedder_schemas)

    for setting in json["settings"]:
        assert setting["name"] in embedder_schemas.keys()
        assert setting["value"] == {}
        expected_schema = embedder_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    # automatically selected embedder
    assert json["selected_configuration"] == "EmbedderDumbConfig"


def test_get_embedder_settings_non_existent(secure_client, secure_client_headers):
    non_existent_embedder_name = "EmbedderNonExistentConfig"
    response = secure_client.get(f"/embedder/settings/{non_existent_embedder_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_embedder_name} not supported" in json["detail"]


def test_get_embedder_settings(secure_client, secure_client_headers):
    embedder_name = "EmbedderDumbConfig"
    response = secure_client.get(f"/embedder/settings/{embedder_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == embedder_name
    assert json["value"] == {}  # Dumb Embedder has indeed an empty config (no options)
    assert json["scheme"]["languageEmbedderName"] == embedder_name
    assert json["scheme"]["type"] == "object"


def test_upsert_embedder_settings(secure_client, secure_client_headers):
    # set a different embedder from default one (same class different size)
    new_embedder = "EmbedderFakeConfig"
    embedder_config = {"size": 64}
    response = secure_client.put(
        f"/embedder/settings/{new_embedder}", json=embedder_config, headers=secure_client_headers
    )
    json = response.json()

    # verify success
    assert response.status_code == 200
    assert json["name"] == new_embedder
    assert json["value"]["size"] == embedder_config["size"]

    # retrieve all embedders settings to check if it was saved in DB
    response = secure_client.get("/embedder/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_embedder
    saved_config = [c for c in json["settings"] if c["name"] == new_embedder]
    assert saved_config[0]["value"]["size"] == embedder_config["size"]

    # check also specific embedder endpoint
    response = secure_client.get(f"/embedder/settings/{new_embedder}", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_embedder
    assert json["value"]["size"] == embedder_config["size"]
    assert json["scheme"]["languageEmbedderName"] == new_embedder


@pytest.mark.asyncio
async def test_upsert_embedder_settings_updates_collections(secure_client, lizard):
    agent_id = "test_embedder_settings_updates_collections"
    cheshire_cat = await lizard.create_cheshire_cat(agent_id)

    headers = {"X-Agent-ID": agent_id, "Authorization": f"Bearer {api_key}"}

    embedded_procedures_before = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.PROCEDURAL)
    )
    assert embedded_procedures_before > 0

    # set a new file manager
    file_manager_name = "LocalFileManagerConfig"
    response = secure_client.put(
        f"/file_manager/settings/{file_manager_name}", headers=headers, json={},
    )
    assert response.status_code == 200

    # upload a file to the Knowledge Base of the agent
    content_type = "text/plain"
    file_name = "sample.txt"
    response, _ = send_file(file_name, content_type, secure_client, headers)
    assert response.status_code == 200

    response, _ = send_file("sample.pdf", "application/pdf", secure_client, headers, ch_id=chat_id)
    assert response.status_code == 200
    declarative_memories_before = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.DECLARATIVE)
    )
    assert declarative_memories_before > 0
    episodic_memories = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.EPISODIC)
    )
    assert episodic_memories > 0

    # check that only the file sent to the agent's RAG exists in the list of files
    res = secure_client.request("GET", "/file_manager", headers=headers)
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 1
    assert any(f["name"] == file_name for f in files)
    assert not any(f["name"] == "sample.pdf" for f in files)

    # set a different embedder from default one (same class different size)
    embedder_config = {"size": 64}
    response = secure_client.put(
        "/embedder/settings/EmbedderFakeConfig", json=embedder_config, headers=headers
    )
    assert response.status_code == 200

    await asyncio.sleep(1)  # give some time for the background tasks to complete

    embedder_procedures_after = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.PROCEDURAL)
    )
    assert embedder_procedures_after == embedded_procedures_before

    declarative_memories_after = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.DECLARATIVE)
    )
    assert declarative_memories_after == declarative_memories_before

    # delete first document
    res = secure_client.request("DELETE", f"/file_manager/files/{file_name}", headers=headers)
    # check memory contents
    assert res.status_code == 200
    json = res.json()
    assert isinstance(json["deleted"], bool)
    declarative_memories = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.DECLARATIVE)
    )
    assert declarative_memories == 0

    # check that the file does not exist anymore in the list of files
    res = secure_client.request("GET", "/file_manager", headers=headers)
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 0


@pytest.mark.asyncio
async def test_upsert_embedder_settings_with_episodic_memory_without_conversation(secure_client, lizard):
    agent_id = "test_embedder_settings_updates_collections"
    cheshire_cat = await lizard.create_cheshire_cat(agent_id)

    headers = {"X-Agent-ID": agent_id, "Authorization": f"Bearer {api_key}"}

    # set a new file manager
    file_manager_name = "LocalFileManagerConfig"
    response = secure_client.put(
        f"/file_manager/settings/{file_manager_name}", headers=headers, json={},
    )
    assert response.status_code == 200

    # upload a file to the Knowledge Base of the agent
    content_type = "text/plain"
    file_name = "sample.txt"
    response, _ = send_file(file_name, content_type, secure_client, headers, ch_id=chat_id)
    assert response.status_code == 200
    episodic_memories_before = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.EPISODIC)
    )
    assert episodic_memories_before > 0

    # check that the file does not in the list of files, because it is episodic
    res = secure_client.request("GET", "/file_manager", headers=headers)
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 0

    # set a different embedder from default one (same class different size)
    embedder_config = {"size": 64}
    response = secure_client.put(
        "/embedder/settings/EmbedderFakeConfig", json=embedder_config, headers=headers
    )
    assert response.status_code == 200

    await asyncio.sleep(1)  # give some time for the background tasks to complete

    episodic_memories_after = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.EPISODIC)
    )
    assert episodic_memories_after != episodic_memories_before
    assert episodic_memories_after == 0
