import pytest

from tests.utils import just_installed_plugin, create_new_user, new_user_password, agent_id


def test_custom_endpoint_base(client, secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)
    # activate the plugin
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    response = client.get("/custom/endpoint")
    assert response.status_code == 200
    assert response.json()["result"] == "endpoint default prefix"


def test_custom_endpoint_prefix(client, secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)
    # activate the plugin
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    response = client.get("/tests/endpoint")
    assert response.status_code == 200
    assert response.json()["result"] == "endpoint prefix tests"


def test_custom_endpoint_get(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)
    # activate the plugin
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    response = secure_client.get("/tests/crud", headers=secure_client_headers)

    assert response.status_code == 200
    assert response.json()["result"] == "ok"
    assert isinstance(response.json()["stray_user_id"], str)
    assert len(response.json()["stray_user_id"]) == 36


def test_custom_endpoint_post(client, secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)
    # activate the plugin
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    payload = {"name": "the cat", "description" : "it's magic"}
    response = client.post("/tests/crud", json=payload)

    assert response.status_code == 200
    assert response.json()["id"] == 1
    assert response.json()["name"] == "the cat"
    assert response.json()["description"] == "it's magic"


def test_custom_endpoint_put(client, just_installed_plugin):
    payload = {"name": "the cat", "description": "it's magic"}
    response = client.put("/tests/crud/123", json=payload)
    
    assert response.status_code == 200
    assert response.json()["id"] == 123
    assert response.json()["name"] == "the cat"
    assert response.json()["description"] == "it's magic"

def test_custom_endpoint_delete(client, just_installed_plugin):
    response = client.delete("/tests/crud/123")
    
    assert response.status_code == 200
    assert response.json()["result"] == "ok"
    assert response.json()["deleted_id"] == 123


@pytest.mark.parametrize("switch_type", ["deactivation", "uninstall"])
def test_custom_endpoints_on_plugin_deactivation_or_uninstall(switch_type, secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)
    # activate the plugin
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # endpoints added via mock_plugin (verb, endpoint, payload)
    custom_endpoints = [
        ("GET", "/custom/endpoint", None),
        ("GET", "/tests/endpoint", None),
        ("GET", "/tests/crud", None),
        ("POST", "/tests/crud", {"name": "the cat", "description": "it's magic"}),
        ("PUT", "/tests/crud/123", {"name": "the cat", "description": "it's magic"}),
        ("DELETE", "/tests/crud/123", None),
    ]

    # custom endpoints are active
    for verb, endpoint, payload in custom_endpoints:
        response = secure_client.request(verb, endpoint, json=payload, headers=secure_client_headers)
        assert response.status_code == 200

    if switch_type == "deactivation":
        # deactivate plugin
        response = secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)
        assert response.status_code == 200
    else:
        # uninstall plugin
        response = secure_client.delete("/admins/plugins/mock_plugin", headers=secure_client_headers)
        assert response.status_code == 200

    # no more custom endpoints
    for verb, endpoint, payload in custom_endpoints:
        response = secure_client.request(verb, endpoint, json=payload, headers=secure_client_headers)
        assert response.status_code == 404


@pytest.mark.parametrize("resource", ["PLUGINS", "LLM"])
@pytest.mark.parametrize("permission", ["LIST", "DELETE"])
def test_custom_endpoint_permissions(resource, permission, client, secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)
    # activate the plugin
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # create user with permissions
    data = create_new_user(
        secure_client, "/users", headers=secure_client_headers, permissions={resource: [permission]}
    )
    creds = {"username": data["username"], "password": new_user_password}

    # get jwt for user
    response = client.post("/auth/token", json=creds, headers={"agent_id": agent_id})
    received_token = response.json()["access_token"]

    # use endpoint (requires PLUGINS resource and LIST permission)
    response = client.get("/tests/crud", headers={"Authorization": f"Bearer {received_token}", "agent_id": agent_id})
    if resource == "PLUGINS" and permission == "LIST":
        assert response.status_code == 200
    else:
        assert response.status_code == 403
