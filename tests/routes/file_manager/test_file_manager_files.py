from tests.utils import send_file, get_declarative_memory_contents


def test_file_deleted(secure_client, secure_client_headers):
    # set file_manager_name = "LocalFileManagerConfig"
    file_manager_name = "LocalFileManagerConfig"
    response = secure_client.put(
        f"/file_manager/settings/{file_manager_name}", headers=secure_client_headers, json={},
    )
    assert response.status_code == 200

    content_type = "application/pdf"
    response, file_path = send_file("sample.pdf", content_type, secure_client, secure_client_headers)
    assert response.status_code == 200

    # check memory contents
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) > 0

    # check that the file exists in the list of files
    res = secure_client.request(
        "GET", "/file_manager", headers=secure_client_headers
    )
    assert res.status_code == 200
    json = res.json()
    print(json)
    files = json["files"]
    assert len(files) == 1
    assert any(f["name"] == "sample.pdf" for f in files)

    # delete first document
    res = secure_client.request(
        "DELETE", "/file_manager/files/sample.pdf", headers=secure_client_headers
    )
    # check memory contents
    assert res.status_code == 200
    json = res.json()
    assert isinstance(json["deleted"], bool)
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 0

    # check that the file does not exist anymore in the list of files
    res = secure_client.request(
        "GET", "/file_manager", headers=secure_client_headers
    )
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 0


def test_files_deleted(secure_client, secure_client_headers):
    # set file_manager_name = "LocalFileManagerConfig"
    file_manager_name = "LocalFileManagerConfig"
    response = secure_client.put(
        f"/file_manager/settings/{file_manager_name}", headers=secure_client_headers, json={},
    )
    assert response.status_code == 200

    content_type = "application/pdf"
    response, file_path = send_file("sample.pdf", content_type, secure_client, secure_client_headers)
    assert response.status_code == 200

    # upload another document
    with open(file_path, "rb") as f:
        files = {"file": ("sample2.pdf", f, content_type)}
        response = secure_client.post("/rabbithole/", files=files, headers=secure_client_headers)
        assert response.status_code == 200

    # check memory contents
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) > 0

    # check that the files exist in the list of files
    res = secure_client.request(
        "GET", "/file_manager", headers=secure_client_headers
    )
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 2
    assert any(f["name"] == "sample.pdf" for f in files)
    assert any(f["name"] == "sample2.pdf" for f in files)

    # delete all documents
    res = secure_client.request(
        "DELETE", "/file_manager/files", headers=secure_client_headers
    )
    # check memory contents
    assert res.status_code == 200
    json = res.json()
    assert isinstance(json["deleted"], bool)
    declarative_memories = get_declarative_memory_contents(secure_client, secure_client_headers)
    assert len(declarative_memories) == 0

    # check that the files do not exist anymore in the list of files
    res = secure_client.request(
        "GET", "/file_manager", headers=secure_client_headers
    )
    assert res.status_code == 200
    json = res.json()
    files = json["files"]
    assert len(files) == 0
