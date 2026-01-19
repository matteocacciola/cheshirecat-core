from cat.services.memory.models import VectorMemoryType

from tests.utils import send_file, get_memory_contents


def check_file_deleted(secure_client, secure_client_headers, collection: VectorMemoryType, ch_id = None):
    # set file_manager_name = "LocalFileManagerConfig"
    file_manager_name = "LocalFileManagerConfig"
    response = secure_client.put(
        f"/file_manager/settings/{file_manager_name}", headers=secure_client_headers, json={},
    )
    assert response.status_code == 200

    content_type = "application/pdf"
    response, file_path = send_file(
        "sample.pdf", content_type, secure_client, secure_client_headers, ch_id=ch_id
    )
    assert response.status_code == 200

    headers = secure_client_headers
    if ch_id:
        headers |= {"X-Chat-ID": ch_id}

    # check memory contents
    memories = get_memory_contents(secure_client, headers, collection)
    assert len(memories) > 0

    # check that the file exists in the list of files
    res = secure_client.request("GET", "/file_manager", headers=headers)
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 1
    assert any(f["name"] == "sample.pdf" for f in files)

    # delete first document
    res = secure_client.request("DELETE", "/file_manager/files/sample.pdf", headers=headers)
    # check memory contents
    assert res.status_code == 200
    json = res.json()
    assert isinstance(json["deleted"], bool)
    memories = get_memory_contents(secure_client, headers, collection)
    assert len(memories) == 0

    # check that the file does not exist anymore in the list of files
    res = secure_client.request("GET", "/file_manager", headers=headers)
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 0


def check_files_deleted(secure_client, secure_client_headers, collection: VectorMemoryType, ch_id = None):
    # set file_manager_name = "LocalFileManagerConfig"
    file_manager_name = "LocalFileManagerConfig"
    response = secure_client.put(f"/file_manager/settings/{file_manager_name}", headers=secure_client_headers, json={})
    assert response.status_code == 200

    content_type = "application/pdf"
    response, file_path = send_file("sample.pdf", content_type, secure_client, secure_client_headers, ch_id=ch_id)
    assert response.status_code == 200

    # check memory contents
    headers = secure_client_headers
    if ch_id:
        headers |= {"X-Chat-ID": ch_id}

    # upload another document
    with open(file_path, "rb") as f:
        files = {"file": ("sample2.pdf", f, content_type)}
        response = secure_client.post("/rabbithole/", files=files, headers=headers)
        assert response.status_code == 200

    # check memory contents
    memories = get_memory_contents(secure_client, headers, collection)
    assert len(memories) > 0

    # check that the files exist in the list of files
    res = secure_client.request("GET", "/file_manager", headers=headers)
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 2
    assert any(f["name"] == "sample.pdf" for f in files)
    assert any(f["name"] == "sample2.pdf" for f in files)

    # delete all documents
    res = secure_client.request("DELETE", "/file_manager/files", headers=headers)
    # check memory contents
    assert res.status_code == 200
    json = res.json()
    assert isinstance(json["deleted"], bool)
    memories = get_memory_contents(secure_client, headers, collection)
    assert len(memories) == 0

    # check that the files do not exist anymore in the list of files
    res = secure_client.request("GET", "/file_manager", headers=headers)
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 0


def test_file_deleted(secure_client, secure_client_headers):
    check_file_deleted(secure_client, secure_client_headers, VectorMemoryType.DECLARATIVE)


def test_file_chat_deleted(secure_client, secure_client_headers, stray_no_memory):
    check_file_deleted(secure_client, secure_client_headers, VectorMemoryType.EPISODIC, ch_id=stray_no_memory.id)


def test_files_deleted(secure_client, secure_client_headers):
    check_files_deleted(secure_client, secure_client_headers, VectorMemoryType.DECLARATIVE)


def test_files_chat_deleted(secure_client, secure_client_headers, stray_no_memory):
    check_files_deleted(secure_client, secure_client_headers, VectorMemoryType.EPISODIC, ch_id=stray_no_memory.id)
