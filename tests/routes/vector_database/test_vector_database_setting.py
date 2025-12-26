from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.services.factory.vector_db import VectorDatabaseFactory

from tests.utils import create_new_user, new_user_password, agent_id


def test_get_all_vector_databases_settings(secure_client, secure_client_headers, cheshire_cat):
    vector_dbs_schemas = VectorDatabaseFactory(cheshire_cat.plugin_manager).get_schemas()

    response = secure_client.get("/vector_database/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(vector_dbs_schemas)

    for setting in json["settings"]:
        assert setting["name"] in vector_dbs_schemas.keys()
        expected_schema = vector_dbs_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    assert json["selected_configuration"] == "QdrantConfig"


def test_get_vector_database_settings_non_existent(secure_client, secure_client_headers):
    non_existent_vector_db_name = "VectorDBNonExistentConfig"
    response = secure_client.get(
        f"/vector_database/settings/{non_existent_vector_db_name}", headers=secure_client_headers
    )
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_vector_db_name} not supported" in json["detail"]


def test_get_vector_database_settings(secure_client, secure_client_headers):
    vector_db_name = "QdrantConfig"
    response = secure_client.get(f"/vector_database/settings/{vector_db_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == vector_db_name
    assert json["scheme"]["vectorDatabaseName"] == vector_db_name
    assert json["scheme"]["type"] == "object"


def test_upsert_vector_database_settings_success(secure_client, secure_client_headers):
    new_vector_db = "QdrantConfig"
    payload = {
        "host": "localhost",
        "port": 6333,
        "api_key": "this_is_a_test_api_key",
        "client_timeout": 10,
    }
    response = secure_client.put(
        f"/vector_database/settings/{new_vector_db}", json=payload, headers=secure_client_headers
    )

    # check immediate response
    json = response.json()
    assert response.status_code == 200
    assert json["name"] == new_vector_db
    assert json["value"]["host"] == payload["host"]
    assert json["value"]["port"] == payload["port"]
    assert "api_key" in json["value"]
    assert json["value"]["client_timeout"] == payload["client_timeout"]

    # retrieve all Vector databases settings to check if it was saved in DB
    response = secure_client.get("/vector_database/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_vector_db
    saved_config = [c for c in json["settings"] if c["name"] == new_vector_db]
    assert saved_config[0]["value"]["host"] == payload["host"]
    assert saved_config[0]["value"]["port"] == payload["port"]
    assert "api_key" in saved_config[0]["value"]
    assert saved_config[0]["value"]["client_timeout"] == payload["client_timeout"]

    # check also specific Vector database endpoint
    response = secure_client.get(f"/vector_database/settings/{new_vector_db}", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_vector_db
    assert json["value"]["host"] == payload["host"]
    assert json["value"]["port"] == payload["port"]
    assert "api_key" in json["value"]
    assert json["value"]["client_timeout"] == payload["client_timeout"]
    assert json["scheme"]["vectorDatabaseName"] == new_vector_db


def test_forbidden_access_no_auth(client):
    response = client.get("/vector_database/settings")
    assert response.status_code == 401


def test_granted_access_on_permissions(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(
        secure_client, "/users", headers=secure_client_headers, permissions={"VECTOR_DATABASE": ["LIST"]}
    )
    res = client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = client.get(
        "/vector_database/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id}
    )
    assert response.status_code == 200


def test_forbidden_access_no_permission(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(secure_client, "/users", headers=secure_client_headers)
    res = client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = client.get(
        "/vector_database/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


def test_forbidden_access_wrong_permissions(secure_client, secure_client_headers, client):
    # create user
    data = create_new_user(
        secure_client, "/users", headers=secure_client_headers, permissions={"VECTOR_DATABASE": ["READ"]}
    )
    res = client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = client.get(
        "/vector_database/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id}
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"
