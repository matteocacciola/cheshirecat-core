from json import dumps
from fastapi.encoders import jsonable_encoder

from cat.services.service_factory import ServiceFactory

from tests.utils import create_new_user, new_user_password, agent_id


async def test_get_all_llm_settings(secure_client, secure_client_headers, cheshire_cat):
    sf = ServiceFactory(
        agent_key=cheshire_cat.agent_key,
        hook_manager=cheshire_cat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_llms",
        setting_category="llm",
        schema_name="languageModelName",
    )
    llms_schemas = await sf.get_schemas()

    response = await secure_client.get("/llm/settings", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(llms_schemas)

    for setting in json["settings"]:
        assert setting["name"] in llms_schemas.keys()
        assert setting["value"] == {}
        expected_schema = llms_schemas[setting["name"]]
        assert dumps(jsonable_encoder(expected_schema)) == dumps(setting["scheme"])

    assert json["selected_configuration"] == "LLMDefaultConfig"


async def test_get_llm_settings_non_existent(secure_client, secure_client_headers, cheshire_cat):
    non_existent_llm_name = "LLMNonExistentConfig"
    response = await secure_client.get(f"/llm/settings/{non_existent_llm_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 400
    assert f"{non_existent_llm_name} not supported" in json["detail"]


async def test_get_llm_settings(secure_client, secure_client_headers, cheshire_cat):
    llm_name = "LLMDefaultConfig"
    response = await secure_client.get(f"/llm/settings/{llm_name}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert json["name"] == llm_name
    assert json["value"] == {}
    assert json["scheme"]["languageModelName"] == llm_name
    assert json["scheme"]["type"] == "object"


async def test_upsert_llm_settings_success(secure_client, secure_client_headers, cheshire_cat):
    # set a different LLM
    new_llm = "LLMDefaultConfig"
    response = await secure_client.put(f"/llm/settings/{new_llm}", headers=secure_client_headers)

    # check immediate response
    json = response.json()
    assert response.status_code == 200
    assert json["name"] == new_llm

    # retrieve all LLMs settings to check if it was saved in DB
    response = await secure_client.get("/llm/settings", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert json["selected_configuration"] == new_llm

    # check also specific LLM endpoint
    response = await secure_client.get(f"/llm/settings/{new_llm}", headers=secure_client_headers)
    assert response.status_code == 200
    json = response.json()
    assert json["name"] == new_llm
    assert json["scheme"]["languageModelName"] == new_llm


async def test_forbidden_access_no_auth(client, cheshire_cat):
    response = await client.get("/llm/settings")
    assert response.status_code == 401


async def test_granted_access_on_permissions(secure_client, secure_client_headers, client, cheshire_cat):
    # create user
    data = await create_new_user(secure_client, headers=secure_client_headers, permissions={"LLM": ["READ"]})
    res = await client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = await client.get("/llm/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id})
    assert response.status_code == 200


async def test_forbidden_access_no_permission(secure_client, secure_client_headers, client, cheshire_cat):
    # create user
    data = await create_new_user(secure_client, headers=secure_client_headers)
    res = await client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = await client.get("/llm/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id})
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"


async def test_forbidden_access_wrong_permissions(secure_client, secure_client_headers, client, cheshire_cat):
    # create user
    data = await create_new_user(secure_client, headers=secure_client_headers, permissions={"LLM": ["DELETE"]})
    res = await client.post("/auth/token", json={"username": data["username"], "password": new_user_password})
    received_token = res.json()["access_token"]

    response = await client.get("/llm/settings", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id})
    assert response.status_code == 403
    assert response.json()["detail"] == "Forbidden"
