import pytest

from cat.env import get_env

# test endpoints with different user permissions
# NOTE: we are using here the secure_client:
# - CCAT_API_KEY is active
# - we will auth with JWT


@pytest.mark.parametrize("endpoint", [
    {
        "method": "GET",
        "path": "/admins/users",
        "payload": None
    },
    {
        "method": "GET",
        "path": "/admins/users/ID_PLACEHOLDER",
        "payload": None
    },
    {
        "method": "POST",
        "path": "/admins/users",
        "payload": {"username": "Alice", "password": "12345"}
    },
    {
        "method": "PUT",
        "path": "/admins/users/ID_PLACEHOLDER",
        "payload": {"username": "Alice2"}
    },
    {
        "method": "DELETE",
        "path": "/admins/users/ID_PLACEHOLDER",
        "payload": None
    }
])


def test_admins_permissions(secure_client, endpoint):
    credentials = {"username": "admin", "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD")}

    # create new admin that will be edited by calling the endpoints
    # we create it using directly CCAT_API_KEY
    response = secure_client.post(
        "/admins/users",
        json={"username": "Caterpillar", "password": "U R U"},
        headers={"Authorization": f"Bearer {get_env('CCAT_API_KEY')}"},
    )
    assert response.status_code == 200
    target_admin_id = response.json()["id"]

    # tests for `admin` and `user` using the endpoints

    # no JWT, no pass
    res = secure_client.request(
        endpoint["method"],
        endpoint["path"].replace("ID_PLACEHOLDER", target_admin_id),
        json=endpoint["payload"]
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "Invalid Credentials"

    # obtain JWT
    res = secure_client.post("/admins/auth/token", json=credentials, headers={"agent_id": "core"})
    assert res.status_code == 200
    jwt = res.json()["access_token"]

    # now using JWT
    res = secure_client.request(
        endpoint["method"],
        endpoint["path"].replace("ID_PLACEHOLDER", target_admin_id),
        json=endpoint["payload"],
        headers={"Authorization": f"Bearer {jwt}"} # using credentials
    )

    assert res.status_code == 200
