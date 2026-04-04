import json
import os
import pytest
from httpx_ws import WebSocketDisconnect

from cat.auth.permissions import get_base_permissions
from cat.env import get_env

from tests.conftest import api_key
from tests.utils import send_websocket_message, agent_id, create_new_user, new_user_password, http_message


def set_api_key(key: str, value: str) -> str | None:
    current_api_key = get_env(key)
    # set CAT_API_KEY
    os.environ[key] = value

    return current_api_key


def reset_api_key(key, value: str | None) -> None:
    # remove CAT_API_KEY
    if value:
        os.environ[key] = value
    else:
        del os.environ[key]


async def test_api_key_http(secure_client, client, cheshire_cat):
    await create_new_user(
        secure_client,
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )

    old_api_key = set_api_key("CAT_API_KEY", api_key)

    header_name = "Authorization"
    key_prefix = "Bearer"

    wrong_headers = [
        {}, # no key
        {header_name: f"{key_prefix} wrong"}, # wrong key
    ]

    # all the previous headers result in a 403
    for headers in wrong_headers:
        status_code, json = await http_message(secure_client, {"text": "hey"}, headers | {"X-Agent-ID": agent_id})
        assert status_code == 401
        assert json["detail"] == "Unauthorized"

    # allow access if CAT_API_KEY is right
    res = await client.post(
        "/auth/token", json={"username": "user", "password": new_user_password},
    )
    received_token = res.json()["access_token"]

    headers = {header_name: f"{key_prefix} {received_token}"}
    status_code, json = await http_message(client, {"text": "hey"}, headers | {"X-Agent-ID": agent_id})
    assert status_code == 200
    assert json["chat_id"] is not None
    assert "You did not configure" in json["message"]["text"]

    reset_api_key("CAT_API_KEY", old_api_key)


async def test_api_key_ws(secure_client, secure_client_headers, client, cheshire_cat):
    await create_new_user(
        secure_client,
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )

    # set CAT_API_KEY
    old_api_key = set_api_key("CAT_API_KEY", api_key)

    mex = {"text": "Where do I go?"}

    wrong_tokens = [
        "", # no key
        "wrong", # wrong token
    ]

    for token in wrong_tokens:
        with pytest.raises((WebSocketDisconnect, ExceptionGroup)):
            await send_websocket_message(mex, secure_client, token)

    # allow access if CAT_API_KEY is right
    res = await client.post(
        "/auth/token", json={"username": "user", "password": new_user_password},
    )
    received_token = res.json()["access_token"]

    res = await send_websocket_message(mex, secure_client, received_token)
    content = json.loads(res["content"])

    assert content["chat_id"] is not None
    assert "You did not configure" in content["message"]["text"]

    reset_api_key("CAT_API_KEY", old_api_key)
