import time
import uuid

import pytest
from starlette.websockets import WebSocketDisconnect

from cat.auth.permissions import get_base_permissions
from cat.db.cruds import users as crud_users

from tests.utils import (
    send_websocket_message,
    send_n_websocket_messages,
    agent_id,
    api_key,
    create_new_user,
)


def check_correct_websocket_reply(reply):
    for k in ["type", "text", "why"]:
        assert k in reply.keys()

    assert reply["type"] != "error"
    assert isinstance(reply["text"], str)
    assert "You did not configure" in reply["text"]

    # why
    why = reply["why"]
    assert {"input", "intermediate_steps", "memory"} == set(why.keys())
    assert isinstance(why["input"], str)
    assert isinstance(why["intermediate_steps"], list)
    assert isinstance(why["memory"], list)


def test_websocket(secure_client, secure_client_headers):
    user = create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )

    msg = {"text": "It's late! It's late", "image": "tests/mocks/sample.png"}
    # send websocket message
    res = send_websocket_message(msg, secure_client, api_key, query_params={"user_id": user["id"]})

    assert res["agent_id"] == agent_id
    assert res["user_id"] is not None
    assert res["chat_id"] is not None
    check_correct_websocket_reply(res["message"])

    # check analytics
    response = secure_client.get("/analytics/llm", headers=secure_client_headers)
    analytics = response.json()
    #{llm_id: {agent_id: {user_id: {chat_id: <content>}}}}
    assert isinstance(analytics, dict)
    llm_id = list(analytics.keys())[0]
    assert llm_id == "default_llm"

    assert agent_id in analytics[llm_id].keys()
    assert analytics[llm_id] is not None
    assert len(analytics[llm_id].keys()) == 1

    user_id = list(analytics[llm_id][agent_id].keys())[0]
    assert user_id is not None
    assert isinstance(analytics[llm_id][agent_id][user_id], dict)

    chat_id = list(analytics[llm_id][agent_id][user_id].keys())[0]
    assert chat_id is not None
    assert isinstance(analytics[llm_id][agent_id][user_id][chat_id], dict)

    # no tokens used since no valid LLM was configured and, then, no LLM call was made
    info = analytics[llm_id][agent_id][user_id][chat_id]
    assert "input_tokens" in info.keys()
    assert info["input_tokens"] == 0
    assert "output_tokens" in info.keys()
    assert info["output_tokens"] == 0
    assert "total_tokens" in info.keys()
    assert info["total_tokens"] == 0
    assert "total_calls" in info.keys()
    assert info["total_calls"] == 1


def test_websocket_with_additional_items_in_message(secure_client):
    user = create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )

    msg = {
        "text": "It's late! It's late",
        "image": "tests/mocks/sample.png",
        "prompt_settings": {"temperature": 0.5}
    }
    # send websocket message
    res = send_websocket_message(msg, secure_client, api_key, query_params={"user_id": user["id"]})

    assert res["agent_id"] == agent_id
    assert res["user_id"] is not None
    assert res["chat_id"] is not None
    check_correct_websocket_reply(res["message"])


def test_websocket_with_non_saved_user(secure_client):
    with pytest.raises(WebSocketDisconnect):
        mocked_user_id = uuid.uuid4()
        user = crud_users.get_user(agent_id, str(mocked_user_id))
        assert user is None

        msg = {"text": "It's late! It's late", "image": "tests/mocks/sample.png"}
        send_websocket_message(msg, secure_client, api_key, {"user_id": mocked_user_id})


def test_websocket_multiple_messages(secure_client):
    user = create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )

    # send websocket message
    replies = send_n_websocket_messages(3, secure_client, query_params={"user_id": user["id"]})

    for res in replies:
        check_correct_websocket_reply(res["message"])


def test_websocket_multiple_connections(secure_client, secure_client_headers, lizard):
    mex = {"text": "It's late!"}

    data = create_new_user(secure_client, "/users", username="Alice", headers=secure_client_headers)
    data2 = create_new_user(secure_client, "/users", username="Caterpillar", headers=secure_client_headers)

    headers = {"Authorization": f"Bearer {api_key}"}
    with secure_client.websocket_connect(f"/ws/{agent_id}?user_id={data['id']}", headers=headers) as websocket:
        # send ws message
        websocket.send_json(mex)

        with secure_client.websocket_connect(f"/ws/{agent_id}?user_id={data2['id']}", headers=headers) as websocket2:
            # send ws message
            websocket2.send_json(mex)
            # get reply
            reply2 = websocket2.receive_json()

            # two connections open
            ws_users = lizard.websocket_manager.connections.keys()
            assert set(ws_users) == {data["id"], data2["id"]}

        # one connection open
        time.sleep(0.5)
        ws_users = lizard.websocket_manager.connections.keys()
        assert set(ws_users) == {data["id"]}

        # get reply
        reply = websocket.receive_json()

    check_correct_websocket_reply(reply["message"])
    check_correct_websocket_reply(reply2["message"])

    # websocket connection is closed
    time.sleep(0.5)
    assert lizard.websocket_manager.connections == {}
