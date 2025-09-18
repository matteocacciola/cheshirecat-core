from cat.auth.permissions import AuthUserInfo
from cat.looking_glass import StrayCat

from tests.utils import send_websocket_message, api_key, agent_id, create_new_user, new_user_password, chat_id


def test_session_creation_from_websocket(
    secure_client, secure_client_headers, client, cheshire_cat, mocked_default_llm_answer_prompt
):
    # create a new user with username CCC
    username = "Alice"
    data = create_new_user(secure_client, "/users", username=username, headers=secure_client_headers)

    # get the token, to be used in the websocket connection
    res = client.post(
        "/auth/token",
        json={"username": data["username"], "password": new_user_password},
        headers={"agent_id": agent_id}
    )
    received_token = res.json()["access_token"]
    user_id = data["id"]

    # send websocket message
    mex = {"text": "Where do I go?"}
    res = send_websocket_message(mex, client, query_params={"token": received_token, "user_id": user_id}, ch_id=chat_id)

    # check response
    assert "You did not configure" in res["content"]

    # verify session
    user = AuthUserInfo(id=user_id, name=data["username"], permissions=data["permissions"])
    stray_cat = StrayCat(user_data=user, agent_id=agent_id, stray_id=chat_id)

    convo = stray_cat.working_memory.history
    assert len(convo) == 2
    assert convo[0].who == "user"
    assert convo[0].content.text == mex["text"]


def test_session_creation_from_http(secure_client, secure_client_headers, cheshire_cat):
    # create a new user with username CCC
    username = "Alice"
    data = create_new_user(secure_client, "/users", username=username, headers=secure_client_headers)
    user_id = data["id"]

    content_type = "text/plain"
    file_name = "sample.txt"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}

        # sending file from Alice
        response = secure_client.post(
            "/rabbithole/",
            files=files,
            headers={"user_id": user_id, "Authorization": f"Bearer {api_key}", "agent_id": agent_id},
        )

    # check response
    assert response.status_code == 200

    # verify session
    user = AuthUserInfo(id=user_id, name=data["username"], permissions=data["permissions"])
    stray_cat = StrayCat(user_data=user, agent_id=agent_id)

    convo = stray_cat.working_memory.history
    assert len(convo) == 0  # no ws message sent from Alice
