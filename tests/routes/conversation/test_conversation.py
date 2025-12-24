import time

from cat import AuthResource, AuthPermission
from cat.auth.permissions import get_base_permissions
from cat.db.cruds import users as crud_users, conversations as crud_conversations

from tests.utils import (
    send_websocket_message,
    agent_id,
    api_key,
    create_new_user,
    new_user_password,
    chat_id,
)


def test_convo_history_absent(secure_client, secure_client_headers):
    # no ws connection, so no convo history available
    response = secure_client.get(f"/conversation/{chat_id}", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert "history" in json
    assert len(json["history"]) == 0


def test_convo_history_no_update_invalid_llm(secure_client, secure_client_headers):
    user = create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )
    message = "It's late! It's late!"

    # send websocket messages
    send_websocket_message(
        {"text": message}, secure_client, api_key, ch_id=chat_id, query_params={"user_id": user["id"]}
    )

    # check conversation history update
    response = secure_client.get(f"/conversation/{chat_id}", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200
    assert "history" in json
    assert len(json["history"]) == 0


def test_convo_history_update(secure_client, secure_client_headers, mocked_default_llm_answer_prompt):
    user = create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )
    message = "It's late! It's late!"

    # send websocket messages
    send_websocket_message(
        {"text": message}, secure_client, api_key, ch_id=chat_id, query_params={"user_id": user["id"]}
    )
    user = crud_users.get_user_by_username(agent_id, "user")

    # check conversation history update
    response = secure_client.get(
        f"/conversation/{chat_id}", headers={**secure_client_headers, **{"X-User-ID": user["id"]}}
    )
    json = response.json()
    assert response.status_code == 200
    assert "history" in json
    assert len(json["history"]) == 2  # mex and reply

    picked_history = json["history"][0]

    assert picked_history["who"] == "user"
    assert picked_history["message"] == message
    assert picked_history["content"]["text"] == message
    assert picked_history["why"] is None
    assert isinstance(picked_history["when"], float)  # timestamp


def test_convo_delete(secure_client, secure_client_headers, mocked_default_llm_answer_prompt):
    user = create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )

    # send websocket messages
    send_websocket_message(
        {"text": "It's late! It's late!"},
        secure_client,
        api_key,
        ch_id=chat_id,
        query_params={"user_id": user["id"]},
    )
    user = crud_users.get_user_by_username(agent_id, "user")

    # delete convo history
    response = secure_client.delete(
        f"/conversation/{chat_id}", headers={**secure_client_headers, **{"X-User-ID": user["id"]}}
    )
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    # check conversation history is empty
    response = secure_client.get(
        f"/conversation/{chat_id}", headers={**secure_client_headers, **{"X-User-ID": user["id"]}}
    )
    json = response.json()
    assert response.status_code == 200
    assert "history" in json
    assert len(json["history"]) == 0

    # check there is not conversation with name = chat_id
    conversation = crud_conversations.get_conversation(agent_id, user["id"], chat_id)
    assert conversation is None


def test_convo_history_by_user(secure_client, secure_client_headers, client, mocked_default_llm_answer_prompt):
    convos = {
        # user_id: n_messages
        "White Rabbit": 2,
        "Alice": 3,
    }

    tokens = {}
    users = {}
    # send websocket messages
    for username, n_messages in convos.items():
        data = create_new_user(
            secure_client,
            "/users",
            username=username,
            headers=secure_client_headers,
            permissions={
                str(AuthResource.CHAT): [str(AuthPermission.READ), str(AuthPermission.WRITE)],
                str(AuthResource.MEMORY): [str(AuthPermission.READ)]
            }
        )
        res = client.post(
            "/auth/token",
            json={"username": data["username"], "password": new_user_password},
        )
        received_token = res.json()["access_token"]
        tokens[username] = received_token
        users[username] = data

        for m in range(n_messages):
            time.sleep(0.1)
            send_websocket_message(
                {"text": f"Mex n.{m} from {username}"},
                client,
                received_token,
                ch_id=chat_id,
            )

    # check conversation history
    for username, n_messages in convos.items():
        response = client.get(
            f"/conversation/{chat_id}",
            headers={"X-Agent-ID": agent_id, "Authorization": f"Bearer {tokens[username]}"},
        )
        json = response.json()
        assert response.status_code == 200
        assert "history" in json
        assert len(json["history"]) == n_messages * 2  # mex and reply
        for m_idx, m in enumerate(json["history"]):
            assert "who" in m
            assert "message" in m
            assert "content" in m
            assert "text" in m["content"]
            if m_idx % 2 == 0:  # even message
                m_number_from_user = int(m_idx / 2)
                assert m["who"] == "user"
                assert m["message"] == f"Mex n.{m_number_from_user} from {username}"
                assert m["content"]["text"] == f"Mex n.{m_number_from_user} from {username}"
            else:
                assert m["who"] == "assistant"

    # delete White Rabbit convo
    response = client.delete(
        f"/conversation/{chat_id}",
        headers={"X-Agent-ID": agent_id, "Authorization": f"Bearer {tokens['White Rabbit']}"},
    )
    assert response.status_code == 403  # user has no permission
    response = secure_client.delete(
        f"/conversation/{chat_id}",
        headers={"X-User-ID": users["White Rabbit"]["id"], "X-Agent-ID": agent_id, "Authorization": f"Bearer {api_key}"},
    )
    assert response.status_code == 200

    # check convo deletion per user
    ### White Rabbit convo is empty
    response = secure_client.get(
        f"/conversation/{chat_id}",
        headers=secure_client_headers | {"X-User-ID": users["White Rabbit"]["id"]},
    )
    json = response.json()
    assert len(json["history"]) == 0
    ### Alice convo still the same
    response = secure_client.get(
        f"/conversation/{chat_id}",
        headers=secure_client_headers | {"X-User-ID": users["Alice"]["id"]},
    )
    json = response.json()
    assert len(json["history"]) == convos["Alice"] * 2


def test_change_name_to_conversation(secure_client, secure_client_headers, client, cheshire_cat):
    user = create_new_user(
        secure_client,
        "/users",
        username="Alice",
        headers=secure_client_headers,
        permissions={
            str(AuthResource.CHAT): [str(AuthPermission.READ), str(AuthPermission.WRITE)],
            str(AuthResource.MEMORY): [str(AuthPermission.WRITE)]
        }
    )
    res = client.post(
        "/auth/token",
        json={"username": user["username"], "password": new_user_password},
    )
    received_token = res.json()["access_token"]

    send_websocket_message(
        {"text": "Hello, Alice!"},
        client,
        received_token,
        ch_id=chat_id,
    )

    current_name = crud_conversations.get_name(agent_id, user["id"], chat_id)  # should be None at first
    assert current_name == chat_id

    # change the name of the conversation
    response = secure_client.post(
        f"/conversation/{chat_id}",
        headers={**secure_client_headers, **{"X-User-ID": user["id"]}},
        json={"name": "this_is_a_new_name"}
    )
    assert response.status_code == 200

    current_name = crud_conversations.get_name(agent_id, user["id"], chat_id)  # should be None at first
    assert current_name == "this_is_a_new_name"


def test_get_empty_conversations(secure_client, secure_client_headers):
    create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )

    user = crud_users.get_user_by_username(agent_id, "user")

    # check conversation history update
    response = secure_client.get(
        "/conversation", headers={**secure_client_headers, **{"X-User-ID": user["id"]}}
    )
    assert response.status_code == 200

    json_response = response.json()
    assert isinstance(json_response, list)
    assert len(json_response) == 0  # no chats for this user


def test_get_conversations(secure_client, secure_client_headers, mocked_default_llm_answer_prompt):
    create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
    )
    user = crud_users.get_user_by_username(agent_id, "user")

    message = "It's late! It's late!"
    # send 3 messages to 3 different chats for the same user
    for _ in range(3):
        # send websocket messages
        send_websocket_message(
            {"text": message}, secure_client, api_key, query_params={"user_id": user["id"]}
        )

    # check all the conversation histories
    response = secure_client.get(
        "/conversation", headers={**secure_client_headers, **{"X-User-ID": user["id"]}}
    )
    assert response.status_code == 200

    json_response = response.json()
    assert isinstance(json_response, list)
    assert len(json_response) == 3

    # sending two more messages to the `chat_id` chat
    for _ in range(2):
        # send websocket messages
        send_websocket_message(
            {"text": message}, secure_client, api_key, query_params={"user_id": user["id"]}, ch_id=chat_id
        )

    # check again all the conversation histories
    response = secure_client.get(
        "/conversation", headers={**secure_client_headers, **{"X-User-ID": user["id"]}}
    )
    assert response.status_code == 200

    json_response = response.json()
    assert len(json_response) == 4

    # check that the `chat_id` chat has 4 messages (2 mex + 2 replies)
    for item in json_response:
        assert item["chat_id"] == item["name"]  # chat_id and name are the same
        ch_id = item["chat_id"]

        if ch_id != chat_id:
            assert item["num_messages"] == 2  # 1 mex + 1 reply
        else:
            assert item["num_messages"] == 4  # 2 mex + 2 replies
