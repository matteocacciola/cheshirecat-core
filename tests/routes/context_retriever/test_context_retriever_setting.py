from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.services.service_factory import ServiceFactory

from tests.utils import create_new_user, new_user_password, agent_id


async def test_get_all_context_retriever_settings(secure_client, secure_client_headers, cheshire_cat):
    sf = ServiceFactory(
        agent_key=cheshire_cat.agent_key,
        hook_manager=cheshire_cat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_context_retrievers",
        setting_category="context_retriever",
        schema_name="contextRetrieverName",
    )
    context_retrievers_schemas = await sf.get_schemas()

    response = await secure_client.get("/context_retriever/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(context_retrievers_schemas)

    for setting in json["settings"]:
        assert setting["name"] in context_retrievers_schemas.keys()
        expected_schema = context_retrievers_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    assert json["selected_configuration"] == "DefaultContextRetrieverSettings"


async def test_get_context_retriever_settings_non_existent(secure_client, secure_client_headers, cheshire_cat):
    non_existent_context_retriever_name = "ContextRetrieverNonExistentConfig"
    response = await secure_client.get(
        f"/context_retriever/settings/{non_existent_context_retriever_name}", headers=secure_client_headers,
    )
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_context_retriever_name} not supported" in json["detail"]


async def test_get_context_retriever_settings(secure_client, secure_client_headers, cheshire_cat):
    context_retriever_name = "DefaultContextRetrieverSettings"
    response = await secure_client.get(
        f"/context_retriever/settings/{context_retriever_name}", headers=secure_client_headers,
    )
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == context_retriever_name
    assert json["scheme"]["contextRetrieverName"] == context_retriever_name
    assert json["scheme"]["type"] == "object"


async def test_forbidden_access_no_auth(client):
    response = await client.get("/context_retriever/settings")
    assert response.status_code == 401


async def test_granted_access_on_permissions(secure_client, secure_client_headers, client, cheshire_cat):
    # create user
    data = await create_new_user(secure_client, headers=secure_client_headers, permissions={"CONTEXT_RETRIEVER": ["READ"]})

    creds = {"username": data["username"], "password": new_user_password}

    res = await client.post("/auth/token", json=creds)
    received_token = res.json()["access_token"]

    response = await client.get(
        "/context_retriever/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id},
    )
    assert response.status_code == 200


async def test_forbidden_access_no_permission(secure_client, secure_client_headers, client, cheshire_cat):
    # create user
    data = await create_new_user(secure_client, headers=secure_client_headers)
    res = await client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = await client.get(
        "/context_retriever/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


async def test_forbidden_access_wrong_permissions(secure_client, secure_client_headers, client, cheshire_cat):
    # create user
    data = await create_new_user(secure_client, headers=secure_client_headers, permissions={"CONTEXT_RETRIEVER": ["DELETE"]})
    res = await client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = await client.get(
        "/context_retriever/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"
