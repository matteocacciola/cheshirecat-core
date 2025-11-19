import json
import pytest

import cat.core_plugins.analytics.cruds.embeddings as crud_embeddings

from tests.utils import agent_id, api_key, chat_id, get_declarative_memory_contents, send_file


def _check_analytics_not_empty(analytics):
    assert len(analytics) > 0
    embedders = analytics.get(agent_id, {}).keys()
    assert len(embedders) == 1
    embedder = list(embedders)[0]

    return analytics[agent_id][embedder]


def _check_analytics(analytics, file_name, num_files = 1):
    analytics_ = _check_analytics_not_empty(analytics)
    assert "files" in analytics_.keys()
    assert len(analytics_["files"].keys()) == num_files
    assert file_name in analytics_["files"].keys()
    assert analytics_["files"][file_name] > 0
    assert "total_embeddings" in analytics_.keys()
    assert analytics_["total_embeddings"] > 0


def _check_on_file_upload(response, file_name, content_type, secure_client, secure_client_headers) -> dict:
    # check response
    assert response.status_code == 200
    json_res = response.json()
    assert json_res["filename"] == file_name
    assert json_res["content_type"] == content_type
    assert "File is being ingested" in json_res["info"]

    # check memory contents
    # check declarative memory is empty
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) > 0

    _check_analytics(crud_embeddings.get_analytics(agent_id), file_name)
    return json_res


def _check_upon_request(secure_client, secure_client_headers, file_name):
    response = secure_client.get("/analytics/embedder", headers=secure_client_headers)
    analytics = response.json()
    _check_analytics(analytics, file_name)


def test_rabbithole_upload_txt(secure_client, secure_client_headers):
    content_type = "text/plain"
    file_name = "sample.txt"
    response, _ = send_file(file_name, content_type, secure_client, secure_client_headers)

    _check_on_file_upload(response, file_name, content_type, secure_client, secure_client_headers)
    _check_upon_request(secure_client, secure_client_headers, file_name)


def test_rabbithole_upload_txt_to_stray(secure_client, secure_client_headers):
    content_type = "text/plain"
    file_name = "sample.txt"
    response, _ = send_file(file_name, content_type, secure_client, secure_client_headers, ch_id=chat_id)

    _check_on_file_upload(response, file_name, content_type, secure_client, secure_client_headers)
    _check_upon_request(secure_client, secure_client_headers, file_name)


@pytest.mark.asyncio
async def test_rabbithole_upload_pdf(lizard, secure_client, secure_client_headers):
    cat = await lizard.create_cheshire_cat("another_agent_test")

    content_type = "application/pdf"
    file_name = "sample.pdf"
    response, _ = send_file(file_name, content_type, secure_client, secure_client_headers)

    _check_on_file_upload(response, file_name, content_type, secure_client, secure_client_headers)
    _check_upon_request(secure_client, secure_client_headers, file_name)

    # declarative memory should be empty for another agent
    declarative_memories = get_declarative_memory_contents(
        secure_client, {"agent_id": "another_agent_test", "Authorization": f"Bearer {api_key}"}
    )
    assert len(declarative_memories) == 0

    await cat.destroy_memory()


def test_rabbithole_upload_batch_one_file(secure_client, secure_client_headers):
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = [("files", (file_name, f, content_type))]
        response = secure_client.post("/rabbithole/batch", files=files, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    json_res = response.json()
    assert len(json_res) == 1
    assert file_name in json_res
    assert json_res[file_name]["filename"] == file_name
    assert json_res[file_name]["content_type"] == content_type
    assert "File is being ingested" in json_res[file_name]["info"]

    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) > 0

    _check_analytics(crud_embeddings.get_analytics(agent_id), file_name)


def test_rabbithole_upload_batch_multiple_files(secure_client, secure_client_headers):
    files = []
    files_to_upload = {"sample.pdf": "application/pdf", "sample.txt": "application/txt"}
    for file_name in files_to_upload:
        content_type = files_to_upload[file_name]
        file_path = f"tests/mocks/{file_name}"
        files.append(("files", (file_name, open(file_path, "rb"), content_type)))

    response = secure_client.post("/rabbithole/batch", files=files, headers=secure_client_headers)

    # check response
    assert response.status_code == 200
    json_res = response.json()
    assert len(json_res) == len(files_to_upload)
    for file_name in files_to_upload:
        assert file_name in json_res
        assert json_res[file_name]["filename"] == file_name
        assert json_res[file_name]["content_type"] == files_to_upload[file_name]
        assert "File is being ingested" in json_res[file_name]["info"]

    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) > 0

    analytics = crud_embeddings.get_analytics(agent_id)
    _check_analytics_not_empty(analytics)
    for file_name in files_to_upload:
        _check_analytics(analytics, file_name, num_files=len(files_to_upload))


def test_rabbithole_upload_doc_with_metadata(secure_client, secure_client_headers):
    content_type = "application/pdf"
    file_name = "sample.pdf"

    metadata = {
        "source": file_name,
        "title": "Test title",
        "author": "Test author",
        "year": 2020,
    }
    # upload file endpoint only accepts form-encoded data
    payload = {"metadata": json.dumps(metadata)}

    response, _ = send_file(file_name, content_type, secure_client, secure_client_headers, payload)

    # check response
    assert response.status_code == 200

    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) > 0
    for dm in declarative_memories:
        for k, v in metadata.items():
            assert "when" in dm["metadata"]
            assert "source" in dm["metadata"]
            assert dm["metadata"][k] == v


def test_rabbithole_upload_docs_batch_with_metadata(secure_client, secure_client_headers):
    files = []
    files_to_upload = {"sample.pdf": "application/pdf", "sample.txt": "application/txt"}
    for file_name in files_to_upload:
        content_type = files_to_upload[file_name]
        file_path = f"tests/mocks/{file_name}"
        files.append(("files", (file_name, open(file_path, "rb"), content_type)))

    metadata = {
        "sample.pdf": {
            "source": "sample.pdf",
            "title": "Test title",
            "author": "Test author",
            "year": 2020
        },
        "sample.txt": {
            "source": "sample.txt",
            "title": "Test title",
            "author": "Test author",
            "year": 2021
        }
    }

    # upload file endpoint only accepts form-encoded data
    payload = {
        "metadata": json.dumps(metadata)
    }

    response = secure_client.post("/rabbithole/batch", files=files, data=payload, headers=secure_client_headers)

    # check response
    assert response.status_code == 200

    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) > 0
    for dm in declarative_memories:
        assert "when" in dm["metadata"]
        assert "source" in dm["metadata"]
        # compare with the metadata of the file
        for k, v in metadata[dm["metadata"]["source"]].items():
            assert dm["metadata"][k] == v
