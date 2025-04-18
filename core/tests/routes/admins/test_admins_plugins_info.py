def test_list_plugins(secure_client, secure_client_headers):
    response = secure_client.get("/admins/plugins", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 200
    for key in ["filters", "installed", "registry"]:
        assert key in json.keys()

    # query
    for key in ["query"]:  # ["query", "author", "tag"]:
        assert key in json["filters"].keys()

    # installed
    assert json["installed"][0]["id"] == "core_plugin"
    assert isinstance(json["installed"][0]["active"], bool)
    assert json["installed"][0]["active"]

    # registry (see more registry tests in `./test_plugins_registry.py`)
    assert isinstance(json["registry"], list)
    assert len(json["registry"]) > 0


def test_get_plugin_id(secure_client, secure_client_headers):
    response = secure_client.get("/admins/plugins/core_plugin", headers=secure_client_headers)

    json = response.json()

    assert "data" in json.keys()
    assert json["data"] is not None
    assert json["data"]["id"] == "core_plugin"
    assert isinstance(json["data"]["active"], bool)
    assert json["data"]["active"]


def test_get_non_existent_plugin(secure_client, secure_client_headers):
    response = secure_client.get("/admins/plugins/no_plugin", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 404
    assert json["detail"]["error"] == "Plugin not found"
