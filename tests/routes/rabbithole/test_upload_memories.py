import json
import pytest

from cat.services.memory.utils import VectorMemoryType

from tests.utils import get_collections_names_and_point_count, get_fake_memory_export


# all good memory upload
def test_upload_memory(secure_client, secure_client_headers):
    # upload memories
    file_name = "sample.json"
    content_type = "application/json"
    with open("tests/mocks/sample.json", "rb") as f:
        files = {"file": (file_name, f, content_type)}
        response = secure_client.post("/rabbithole/memory/", files=files, headers=secure_client_headers)

    assert response.status_code == 200
    json_res = response.json()
    assert json_res["filename"] == file_name
    assert json_res["content_type"] == content_type
    assert "Memory is being ingested" in json_res["info"]

    # new declarative memory was saved
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points[str(VectorMemoryType.DECLARATIVE)] == 1 # new declarative memory (just uploaded)


# upload a file different from a JSON
def test_upload_memory_check_mimetype(secure_client, secure_client_headers):
    content_type = "text/plain"
    file_name = "sample.txt"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}
        response = secure_client.post("/rabbithole/memory/", files=files, headers=secure_client_headers)
    
    assert response.status_code == 400
    assert (
        f"MIME type {content_type} not supported." in response.json()["detail"]
    )


# upload memory with a different embedder
def test_upload_memory_check_embedder(secure_client, secure_client_headers, cheshire_cat):
    # Create fake memory
    another_embedder = "AnotherEmbedder"
    fake_memory = get_fake_memory_export(secure_client, embedder_name=another_embedder)

    with pytest.raises(Exception) as e:
        response = secure_client.post(
            "/rabbithole/memory/",
            files={
                "file": ("test_file.json", json.dumps(fake_memory), "application/json")
            },
            headers = secure_client_headers
        )
        assert response.status_code == 200

    # ...but found a different embedder
    assert (
        f"Embedder mismatch: file embedder {another_embedder} is different from DumbEmbedder"
        in str(e.value)
    )
    # and did not update collection
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points[str(VectorMemoryType.DECLARATIVE)] == 0


def test_upload_memory_check_dimensionality(secure_client, secure_client_headers, cheshire_cat):
    # Create fake memory
    wrong_dim = 9
    fake_memory = get_fake_memory_export(secure_client, dim=wrong_dim)

    with pytest.raises(Exception) as e:
        response = secure_client.post(
            "/rabbithole/memory/",
            files={
                "file": ("test_file.json", json.dumps(fake_memory), "application/json")
            },
            headers=secure_client_headers
        )
        assert response.status_code == 200

    # ...but found a different embedder
    assert "Embedding size mismatch" in str(e.value)
    # and did not update collection
    collections_n_points = get_collections_names_and_point_count(secure_client, secure_client_headers)
    assert collections_n_points[str(VectorMemoryType.DECLARATIVE)] == 0



