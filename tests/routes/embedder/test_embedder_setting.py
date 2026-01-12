from json import dumps
import pytest
from fastapi.encoders import jsonable_encoder

from cat.services.memory.utils import VectorMemoryType
from cat.services.service_factory import ServiceFactory

from tests.utils import send_file


def test_get_all_embedder_settings(secure_client, secure_client_headers, lizard):
    embedder_schemas = ServiceFactory(
        lizard.plugin_manager,
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
async def test_upsert_embedder_settings_updates_collections(secure_client, secure_client_headers, lizard):
    agent_id = "test_embedder_settings_updates_collections"
    cheshire_cat = await lizard.create_cheshire_cat(agent_id)

    headers = secure_client_headers| {"X-Agent-ID": agent_id}

    embedded_procedures_before = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.PROCEDURAL)
    )

    # upload a file into the Knowledge Base of the agent
    content_type = "text/plain"
    file_name = "sample.txt"
    response, _ = send_file(file_name, content_type, secure_client, headers)
    assert response.status_code == 200
    declarative_memories_before = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.DECLARATIVE)
    )

    # set a different embedder from default one (same class different size)
    embedder_config = {"size": 64}
    response = secure_client.put(
        "/embedder/settings/EmbedderFakeConfig", json=embedder_config, headers=secure_client_headers
    )
    assert response.status_code == 200

    embedder_procedures_after = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.PROCEDURAL)
    )
    assert embedder_procedures_after == embedded_procedures_before

    declarative_memories_after = await cheshire_cat.vector_memory_handler.get_tenant_vectors_count(
        str(VectorMemoryType.DECLARATIVE)
    )
    assert declarative_memories_after == declarative_memories_before
