from tests.utils import send_websocket_message, get_collections_names_and_point_count, api_key, send_file


def test_memory_collections_created(secure_client, secure_client_headers):
    # get collections
    response = secure_client.get("/memory/collections", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200

    # check default collections are created
    default_collections = ["declarative", "procedural"]
    assert len(json["collections"]) == len(default_collections)

    # check correct number of default points
    collections_n_points = {c["name"]: c["vectors_count"] for c in json["collections"]}
    # there is at least an embedded tool in procedural collection
    assert collections_n_points["procedural"] == 7
    # all other collections should be empty
    assert collections_n_points["declarative"] == 0


def test_memory_collection_non_existent_clear(secure_client, secure_client_headers):
    non_existent_collection = "nonexistent"
    response = secure_client.delete(f"/memory/collections/{non_existent_collection}", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 404
    assert "Collection does not exist" in json["detail"]["error"]


def test_memory_collection_procedural_has_tools_after_clear(secure_client, secure_client_headers):
    # procedural memory contains one tool (get_the_time)
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["procedural"] == 7

    # delete procedural memory
    response = secure_client.delete("/memory/collections/procedural", headers=secure_client_headers)
    assert response.status_code == 200

    # tool should be automatically re-embedded after memory deletion
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["procedural"] == 7


def test_memory_collections_wipe(
    secure_client, secure_client_headers, mocked_default_llm_answer_prompt
):
    message = {"text": "Meow"}
    send_websocket_message(message, secure_client, {"apikey": api_key})

    # create declarative memories
    send_file("sample.txt", "text/plain", secure_client, secure_client_headers)

    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["procedural"] == 7  # default tool
    assert collections_n_points["declarative"] > 1  # several chunks

    # wipe out all memories
    response = secure_client.delete("/memory/collections", headers=secure_client_headers)
    assert response.status_code == 200

    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points["procedural"] == 7  # default tool is re-embedded
    assert collections_n_points["declarative"] == 0
