from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.services.factory.chunker import ChunkerFactory

from tests.utils import create_new_user, new_user_password, agent_id


def test_get_all_chunker_settings(secure_client, secure_client_headers, cheshire_cat):
    chunkers_schemas = ChunkerFactory(cheshire_cat.plugin_manager).get_schemas()

    response = secure_client.get("/chunking/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(chunkers_schemas)

    for setting in json["settings"]:
        assert setting["name"] in chunkers_schemas.keys()
        expected_schema = chunkers_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    assert json["selected_configuration"] == "RecursiveTextChunkerSettings"


def test_get_chunker_settings_non_existent(secure_client, secure_client_headers):
    non_existent_chunker_name = "ChunkerNonExistentConfig"
    response = secure_client.get(f"/chunking/settings/{non_existent_chunker_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_chunker_name} not supported" in json["detail"]


def test_get_chunker_settings(secure_client, secure_client_headers):
    chunker_name = "RecursiveTextChunkerSettings"
    response = secure_client.get(f"/chunking/settings/{chunker_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == chunker_name
    assert json["value"] == {"chunk_overlap": 64, "chunk_size": 256, "encoding_name": "cl100k_base"}
    assert json["scheme"]["chunkerName"] == chunker_name
    assert json["scheme"]["type"] == "object"


def test_upsert_chunker_settings_success(secure_client, secure_client_headers):
    invented_model_name = "this_should_be_a_model"

    # set a different chunker
    new_llm = "SemanticChunkerSettings"
    payload = {"model_name": invented_model_name}
    response = secure_client.put(f"/chunking/settings/{new_llm}", json=payload, headers=secure_client_headers)

    # check immediate response
    json = response.json()
    assert response.status_code == 200
    assert json["name"] == new_llm
    assert json["value"]["model_name"] == invented_model_name

    # retrieve all LLMs settings to check if it was saved in DB
    response = secure_client.get("/chunking/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_llm
    saved_config = [c for c in json["settings"] if c["name"] == new_llm]
    assert saved_config[0]["value"]["model_name"] == invented_model_name

    # check also specific LLM endpoint
    response = secure_client.get(f"/chunking/settings/{new_llm}", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_llm
    assert json["value"]["model_name"] == invented_model_name
    assert json["scheme"]["chunkerName"] == new_llm


def test_forbidden_access_no_auth(client):
    response = client.get("/chunking/settings")
    assert response.status_code == 401


def test_granted_access_on_permissions(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers, permissions={"CHUNKER": ["LIST"]})

    creds = {"username": data["username"], "password": new_user_password}

    res = client.post("/auth/token", json=creds)
    received_token = res.json()["access_token"]

    response = client.get("/chunking/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id})
    assert response.status_code == 200


def test_forbidden_access_no_permission(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers)
    res = client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = client.get("/chunking/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id})
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


def test_forbidden_access_wrong_permissions(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers, permissions={"CHUNKER": ["READ"]})
    res = client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = client.get("/chunking/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id})
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"
