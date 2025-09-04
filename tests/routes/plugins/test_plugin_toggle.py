from tests.utils import just_installed_plugin


def _check_activation(secure_client, secure_client_headers):
    # GET plugins endpoint lists the plugin
    response = secure_client.get("/plugins", headers=secure_client_headers)
    available_plugins = response.json()["installed"]
    mock_plugin = [p for p in available_plugins if p["id"] == "mock_plugin"][0]
    assert isinstance(mock_plugin["active"], bool)
    assert mock_plugin["active"]  # plugin active

    assert mock_plugin["id"] == "mock_plugin"
    assert len(mock_plugin["hooks"]) == 3
    assert len(mock_plugin["tools"]) == 1
    assert len(mock_plugin["forms"]) == 1
    assert len(mock_plugin["endpoints"]) == 7


def test_toggle_non_existent_plugin(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    response = secure_client.put("/plugins/toggle/no_plugin", headers=secure_client_headers)
    response_json = response.json()

    assert response.status_code == 404
    assert response_json["detail"]["error"] == "Plugin not found"


def test_activate_plugin(secure_client, secure_client_headers):
    # install and activate
    just_installed_plugin(secure_client, secure_client_headers, activate=True)

    _check_activation(secure_client, secure_client_headers)


def test_deactivate_plugin(lizard, secure_client, secure_client_headers):
    # install and activate
    just_installed_plugin(secure_client, secure_client_headers, activate=True)
    core_plugins = lizard.plugin_manager.get_core_plugins_ids()

    # verify that the plugin is active
    response = secure_client.get("/plugins", headers=secure_client_headers)
    available_plugins = response.json()["installed"]
    assert len(available_plugins) == len(core_plugins) + 1  # core plugins and mock_plugin

    # deactivate
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # the mock_plugin is no longer available
    response = secure_client.get("/plugins", headers=secure_client_headers)
    available_plugins = response.json()["installed"]
    assert len(available_plugins) == len(core_plugins)  # core plugins only

    mock_plugin = [p for p in available_plugins if p["id"] == "mock_plugin"]
    assert len(mock_plugin) == 0  # plugin not available


def test_reactivate_plugin(secure_client, secure_client_headers):
    # install and activate
    just_installed_plugin(secure_client, secure_client_headers, activate=True)

    # deactivate
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # re-activate
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)
    _check_activation(secure_client, secure_client_headers)
