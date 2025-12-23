from cat import AuthPermission
from cat.auth.permissions import AuthResource

from tests.utils import (
    create_new_user,
    get_client_admin_headers,
    get_full_permissions,
    new_user_password,
    agent_id,
)


def test_ping_success(client):
    response = client.get("/")
    assert response.status_code == 200

    json_response = response.json()
    assert isinstance(json_response, str)


def test_ping_non_admin_endpoint_with_admin(secure_client, secure_client_headers, client):
    permissions = get_full_permissions()
    permissions[str(AuthResource.PLUGIN)].append(str(AuthPermission.LIST))

    new_admin = create_new_user(
        client, "/admins/users", headers=get_client_admin_headers(client), permissions=permissions
    )

    creds = {
        "username": new_admin["username"],
        "password": new_user_password,
    }

    res = client.post("/auth/token", json=creds)
    assert res.status_code == 200

    res_json = res.json()
    received_token = res_json["access_token"]

    # check the access to the get LLMs endpoint
    response = client.get("/plugins", headers={"Authorization": f"Bearer {received_token}", "X-Agent-ID": agent_id})
    assert response.status_code == 200
