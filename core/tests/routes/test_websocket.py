import time
import uuid

from cat.db.cruds import users as crud_users

from tests.utils import send_websocket_message, send_n_websocket_messages, agent_id, api_key, create_new_user


def check_correct_websocket_reply(reply):
    for k in ["type", "content", "why"]:
        assert k in reply.keys()

    assert reply["type"] != "error"
    assert isinstance(reply["content"], str)
    assert "You did not configure" in reply["content"]

    # why
    why = reply["why"]
    assert {"input", "intermediate_steps", "memory", "model_interactions"} == set(why.keys())
    assert isinstance(why["input"], str)
    assert isinstance(why["intermediate_steps"], list)
    assert isinstance(why["memory"], dict)
    assert {"procedural", "declarative", "episodic"} == set(why["memory"].keys())
    assert isinstance(why["model_interactions"], list)
    
    # model interactions
    for mi in why["model_interactions"]:
        assert mi["model_type"] in ["llm", "embedder"]
        assert isinstance(mi["source"], str)
        assert isinstance(mi["prompt"], list)
        for p in mi["prompt"]:
            assert isinstance(p, str)
        assert isinstance(mi["input_tokens"], int)
        # assert mi["input_tokens"] > 0 # TODO V2: default LLM is not a ChatModel
        assert isinstance(mi["started_at"], float)
        assert mi["started_at"] < time.time()

        if mi["model_type"] == "llm":
            assert isinstance(mi["reply"], str)
            assert "You did not configure" in mi["reply"]
            assert isinstance(mi["output_tokens"], int)
            assert mi["output_tokens"] > 0
            assert isinstance(mi["ended_at"], float)
            assert mi["ended_at"] > mi["started_at"]
            assert mi["source"] == "MemoryAgent.execute"
        else:
            assert mi["model_type"] == "embedder"
            assert isinstance(mi["reply"], list)
            assert isinstance(mi["reply"][0], float)
            assert mi["source"] == "StrayCat.recall_relevant_memories_to_working_memory"


def test_websocket(secure_client):
    msg = {"text": "It's late! It's late", "image": "tests/mocks/sample.png"}
    # send websocket message
    res = send_websocket_message(msg, secure_client, {"apikey": api_key})

    check_correct_websocket_reply(res)


def test_websocket_with_additional_items_in_message(secure_client):
    msg = {
        "text": "It's late! It's late",
        "image": "tests/mocks/sample.png",
        "prompt_settings": {"temperature": 0.5}
    }
    # send websocket message
    res = send_websocket_message(msg, secure_client, {"apikey": api_key})

    check_correct_websocket_reply(res)


def test_websocket_with_new_user(secure_client):
    mocked_user_id = uuid.uuid4()

    user = crud_users.get_user(agent_id, str(mocked_user_id))
    assert user is None

    msg = {"text": "It's late! It's late", "image": "tests/mocks/sample.png"}
    res = send_websocket_message(msg, secure_client, {"apikey": api_key, "user_id": mocked_user_id})

    check_correct_websocket_reply(res)

    user = crud_users.get_user(agent_id, str(mocked_user_id))
    assert user is not None


def test_websocket_multiple_messages(secure_client):
    # send websocket message
    replies = send_n_websocket_messages(3, secure_client)

    for res in replies:
        check_correct_websocket_reply(res)


def test_websocket_multiple_connections(secure_client, secure_client_headers, lizard):
    mex = {"text": "It's late!"}

    data = create_new_user(secure_client, "/users", username="Alice", headers=secure_client_headers)
    data2 = create_new_user(secure_client, "/users", username="Caterpillar", headers=secure_client_headers)

    with secure_client.websocket_connect(f"/ws/{agent_id}?apikey={api_key}&user_id={data['id']}") as websocket:
        # send ws message
        websocket.send_json(mex)

        with secure_client.websocket_connect(f"/ws/{agent_id}?apikey={api_key}&user_id={data2['id']}") as websocket2:
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

    check_correct_websocket_reply(reply)
    check_correct_websocket_reply(reply2)

    # websocket connection is closed
    time.sleep(0.5)
    assert lizard.websocket_manager.connections == {}
