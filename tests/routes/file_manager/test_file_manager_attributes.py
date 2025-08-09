def test_get_file_manager_attributes(secure_client, secure_client_headers, cheshire_cat):
    response = secure_client.get("/file_manager", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    assert isinstance(json["files"], list)
    assert len(json["files"]) == 0
    assert isinstance(json["size"], int)
