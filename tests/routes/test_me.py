from cat.auth.permissions import get_base_permissions

from tests.utils import create_new_user, agent_id, new_user_password


async def test_get_me_success(secure_client, secure_client_headers, client, cheshire_cat):
    user = await create_new_user(
        secure_client,
        "user",
        headers=secure_client_headers,
        permissions=get_base_permissions(),
    )

    res = await client.post(
        "/auth/token",
        json={"username": "user", "password": new_user_password},
    )
    assert res.status_code == 200
    token = res.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/me", headers=headers)

    assert response.status_code == 200
    data = response.json()

    assert data["success"] is True
    assert list(data.keys()) == ["success", "agents", "auto_selected"]
    assert len(data.get("agents", [])) == 1
    assert data["auto_selected"] if len(data.get("agents", [])) == 1 else False

    match = data["agents"][0]
    assert match["agent_name"] == agent_id
    assert match["user"]["id"] == user["id"]
    assert match["user"]["username"] == user["username"]
    assert match["user"]["permissions"] == user["permissions"]
