import json
import os
import pytest

from cheshirecat import utils

from tests.utils import get_declarative_memory_contents, api_key, agent_id, send_file


def test_rabbithole_upload_txt(secure_client, secure_client_headers):
    content_type = "text/plain"
    file_name = "sample.txt"
    response, _ = send_file(file_name, content_type, secure_client, secure_client_headers)

    # check response
    assert response.status_code == 200
    json = response.json()
    assert json["filename"] == file_name
    assert json["content_type"] == content_type
    assert "File is being ingested" in json["info"]

    # check memory contents
    # check declarative memory is empty
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert (
        len(declarative_memories) == 3
    )  # TODO: why txt produces one chunk less than pdf?


@pytest.mark.asyncio
async def test_rabbithole_upload_pdf(lizard, secure_client, secure_client_headers):
    cat = await lizard.create_cheshire_cat("another_agent_test")

    content_type = "application/pdf"
    file_name = "sample.pdf"
    response, _ = send_file(file_name, content_type, secure_client, secure_client_headers)

    # check response
    assert response.status_code == 200
    json = response.json()
    assert json["filename"] == file_name
    assert json["content_type"] == content_type
    assert "File is being ingested" in json["info"]

    # check memory contents: declarative memory is not empty
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 4

    # declarative memory should be empty for another agent
    declarative_memories = get_declarative_memory_contents(
        secure_client, {"agent_id": "another_agent_test", "Authorization": f"Bearer {api_key}"}
    )
    assert len(declarative_memories) == 0

    # assert that cat/data folder exists, it has 1 folder with the name `agent_id` and it has 1 file
    storage_folder = utils.get_file_manager_root_storage_path()
    assert os.path.exists(storage_folder)
    assert len(os.listdir(os.path.join(storage_folder, agent_id))) == 1  # type: ignore

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
    json = response.json()
    assert len(json) == 1
    assert file_name in json
    assert json[file_name]["filename"] == file_name
    assert json[file_name]["content_type"] == content_type
    assert "File is being ingested" in json[file_name]["info"]

    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 4


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
    json = response.json()
    assert len(json) == len(files_to_upload)
    for file_name in files_to_upload:
        assert file_name in json
        assert json[file_name]["filename"] == file_name
        assert json[file_name]["content_type"] == files_to_upload[file_name]
        assert "File is being ingested" in json[file_name]["info"]

    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 7


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
    assert len(declarative_memories) == 4
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
    assert len(declarative_memories) == 7
    for dm in declarative_memories:
        assert "when" in dm["metadata"]
        assert "source" in dm["metadata"]
        # compare with the metadata of the file
        for k, v in metadata[dm["metadata"]["source"]].items():
            assert dm["metadata"][k] == v
