import os
import pytest
from fastapi import WebSocketDisconnect

from cat.env import get_env

from tests.conftest import api_key
from tests.utils import send_websocket_message


# utility to make http requests with some headers
def http_message(client, headers=None):
    response = client.post("/message", headers=headers, json={"text": "hey"})
    return response.status_code, response.json()


def set_api_key(key: str, value: str) -> str | None:
    current_api_key = get_env(key)
    # set CCAT_API_KEY
    os.environ[key] = value

    return current_api_key


def reset_api_key(key, value: str | None) -> None:
    # remove CCAT_API_KEY
    if value:
        os.environ[key] = value
    else:
        del os.environ[key]


def test_api_key_http(secure_client):
    old_api_key = set_api_key("CCAT_API_KEY", api_key)

    header_name = "Authorization"
    key_prefix = "Bearer"

    wrong_headers = [
        {}, # no key
        {header_name: f"{key_prefix} wrong"}, # wrong key
    ]

    # all the previous headers result in a 403
    for headers in wrong_headers:
        status_code, json = http_message(secure_client, headers)
        assert status_code == 403
        assert json["detail"] == "Invalid Credentials"

    # allow access if CCAT_API_KEY is right
    headers = {header_name: f"{key_prefix} {api_key}"}
    status_code, json = http_message(secure_client, headers)
    assert status_code == 200
    assert json["chat_id"] is not None
    assert "You did not configure" in json["message"]["text"]

    reset_api_key("CCAT_API_KEY", old_api_key)


def test_api_key_ws(secure_client, secure_client_headers):
    # set CCAT_API_KEY
    old_api_key = set_api_key("CCAT_API_KEY", api_key)

    mex = {"text": "Where do I go?"}

    wrong_tokens = [
        {}, # no key
        "wrong", # wrong token
    ]

    for token in wrong_tokens:
        with pytest.raises(WebSocketDisconnect):
            send_websocket_message(mex, secure_client, token)

    # allow access if CCAT_API_KEY is right
    res = send_websocket_message(mex, secure_client, api_key)
    assert res["chat_id"] is not None
    assert "You did not configure" in res["message"]["content"]

    reset_api_key("CCAT_API_KEY", old_api_key)
