from cat.core_plugins.march_hare.settings import PluginSettings

from tests.utils import just_installed_plugin
from tests.mocks.mock_plugin.mock_plugin_overrides import MockPluginSettings


# endpoint to get settings and settings schema
def test_get_all_plugin_settings(lizard, secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)
    response = secure_client.get("/plugins/system/settings", headers=secure_client_headers)
    json = response.json()

    installed_plugins = lizard.plugin_manager.get_core_plugins_ids + ["mock_plugin"]

    assert response.status_code == 200
    assert isinstance(json["settings"], list)
    assert len(json["settings"]) == len(installed_plugins)

    for setting in json["settings"]:
        assert setting["name"] in installed_plugins
        if setting["name"] == "mock_plugin":
            assert setting["value"] == {"a": "a", "b": 0}
            assert setting["scheme"] == MockPluginSettings.model_json_schema()
        elif setting["name"] == "march_hare":
            assert setting["value"] == {
                "host": "0.0.0.0",
                "port": 5672,
                "username": "guest",
                "password": "guest",
                "is_tls": False,
                "is_disabled": True,
            }
            assert setting["scheme"] == PluginSettings.model_json_schema()
        elif setting["name"] == "memory":
            assert setting["value"] == {"enable_llm_knowledge": True}
        elif setting["name"] == "white_rabbit":
            assert setting["value"] == {"embed_procedures_every_n_days": 7}
        else:
            assert setting["value"] == {}
            assert setting["scheme"] == {}


def test_get_plugin_settings_non_existent(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    non_existent_plugin = "ghost_plugin"
    response = secure_client.get(f"/plugins/system/settings/{non_existent_plugin}", headers=secure_client_headers)
    json = response.json()

    assert response.status_code == 404
    assert "not found" in json["detail"]


# endpoint to get settings and settings schema
def test_get_plugin_settings(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    response = secure_client.get("/plugins/system/settings/mock_plugin", headers=secure_client_headers)
    response_json = response.json()

    assert response.status_code == 200
    assert response_json["name"] == "mock_plugin"
    assert response_json["value"] == {"a": "a", "b": 0}
    assert response_json["scheme"] == MockPluginSettings.model_json_schema()
