from tests.utils import send_websocket_message, get_collections_names_and_point_count, api_key, send_file


def test_memory_collections_created(secure_client, secure_client_headers):
    # get collections
    response = secure_client.get("/memory/collections", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200

    # check default collections are created
    assert len(json["collections"]) == 1

    # check correct number of default points
    collections_n_points = {c["name"]: c["vectors_count"] for c in json["collections"]}
    # all other collections should be empty
    assert collections_n_points["declarative"] == 0


def test_memory_collection_non_existent_clear(secure_client, secure_client_headers):
    non_existent_collection = "nonexistent"
    response = secure_client.delete(f"/memory/collections/{non_existent_collection}", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 404
    assert "Collection does not exist" in json["detail"]["error"]


def test_memory_collections_wipe(
    secure_client, secure_client_headers, mocked_default_llm_answer_prompt
):
    message = {"text": "Meow"}
    send_websocket_message(message, secure_client, {"apikey": api_key})

    # create declarative memories
    send_file("sample.txt", "text/plain", secure_client, secure_client_headers)

    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["declarative"] > 0  # several chunks

    # wipe out all memories
    response = secure_client.delete("/memory/collections", headers=secure_client_headers)
    assert response.status_code == 200

    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["declarative"] == 0


def test_memory_collections_create(
    secure_client, secure_client_headers, mocked_default_llm_answer_prompt
):
    # create collections
    response = secure_client.post("/memory/collections/this_is_a_test_collection", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200

    assert "name" in json
    assert json["name"] == "this_is_a_test_collection"
    assert "vectors_count" in json
    assert json["vectors_count"] == 0
