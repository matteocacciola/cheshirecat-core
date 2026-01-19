def call_and_check(secure_client, headers):
    response = secure_client.get("/file_manager", headers=headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["files"], list)
    assert len(json["files"]) == 0
    assert isinstance(json["size"], int)


def test_get_file_manager_attributes(secure_client, secure_client_headers, cheshire_cat):
    call_and_check(secure_client, secure_client_headers)


def test_get_file_manager_attributes_for_chat(secure_client, secure_client_headers, cheshire_cat, stray_no_memory):
    headers = secure_client_headers | {"X-Chat-ID": stray_no_memory.id}
    call_and_check(secure_client, headers)
