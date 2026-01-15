from cat.auth.permissions import get_base_permissions
from cat.services.memory.models import VectorMemoryType

from tests.utils import (
    send_websocket_message,
    get_collections_names_and_point_count,
    api_key,
    send_file,
    create_new_user,
    agent_id,
    new_user_password,
)


def test_memory_collections_created(secure_client, secure_client_headers):
    # get collections
    response = secure_client.get("/memory/collections", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 200

    # check default collections are created
    assert len(json["collections"]) == 2

    # check correct number of default points
    collections_n_points = {c["name"]: c["vectors_count"] for c in json["collections"]}
    # all other collections should be empty
    assert collections_n_points[str(VectorMemoryType.DECLARATIVE)] == 0


def test_memory_collection_non_existent_clear(secure_client, secure_client_headers):
    non_existent_collection = "nonexistent"
    response = secure_client.delete(f"/memory/collections/{non_existent_collection}", headers=secure_client_headers)
    json = response.json()
    assert response.status_code == 404
    assert "Collection does not exist" in json["detail"]


def test_memory_collections_wipe(
    secure_client, secure_client_headers, mocked_default_llm_answer_prompt
):
    user = create_new_user(
        secure_client,
        "/users",
        "user",
        headers={"Authorization": f"Bearer {api_key}", "X-Agent-ID": agent_id},
        permissions=get_base_permissions(),
        password=new_user_password,
    )

    message = {"text": "Meow"}
    send_websocket_message(message, secure_client, api_key, query_params={"user_id": user["id"]})

    # create declarative memories
    send_file("sample.txt", "text/plain", secure_client, secure_client_headers)

    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points[str(VectorMemoryType.DECLARATIVE)] > 0  # several chunks

    # wipe out all memories
    response = secure_client.delete("/memory/collections", headers=secure_client_headers)
    assert response.status_code == 200

    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points[str(VectorMemoryType.DECLARATIVE)] == 0


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
