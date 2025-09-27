import pytest

from cat.db.cruds import settings as crud_settings
from cat.db.database import DEFAULT_SYSTEM_KEY

from tests.utils import just_installed_plugin, agent_id


def _check_installed_in_cat(secure_client, secure_client_headers, is_active):
    # GET plugins endpoint lists the plugin
    response = secure_client.get("/plugins", headers=secure_client_headers)
    available_plugins = response.json()["installed"]
    mock_plugin = [p for p in available_plugins if p["id"] == "mock_plugin"][0]
    assert isinstance(mock_plugin["local_info"]["active"], bool)
    assert mock_plugin["local_info"]["active"] == is_active

    assert mock_plugin["id"] == "mock_plugin"
    assert len(mock_plugin["local_info"]["hooks"]) == 3
    assert len(mock_plugin["local_info"]["tools"]) == 1
    assert len(mock_plugin["local_info"]["forms"]) == 1
    assert len(mock_plugin["local_info"]["endpoints"]) == 7


def _check_not_installed_in_cat(lizard, secure_client, secure_client_headers):
    core_plugins = lizard.plugin_manager.get_core_plugins_ids()
    # GET plugins endpoint lists the plugin
    response = secure_client.get("/plugins", headers=secure_client_headers)
    available_plugins = response.json()["installed"]
    assert len(available_plugins) == len(core_plugins)  # core plugins only

    mock_plugin = [p for p in available_plugins if p["id"] == "mock_plugin"]
    assert len(mock_plugin) == 0  # plugin not available


def test_toggle_non_existent_plugin(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    response = secure_client.put("/admins/plugins/toggle/no_plugin", headers=secure_client_headers)
    response_json = response.json()

    assert response.status_code == 404
    assert response_json["detail"] == "Plugin not found"


def test_toggle_plugin(lizard, secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    assert "mock_plugin" in crud_settings.get_setting_by_name(DEFAULT_SYSTEM_KEY, "active_plugins")["value"]

    # toggle plugin for a cheshirecat
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)
    assert "mock_plugin" in crud_settings.get_setting_by_name(agent_id, "active_plugins")["value"]
    _check_installed_in_cat(secure_client, secure_client_headers, True)

    # toggle plugin (deactivate) on a system level
    response = secure_client.put("/admins/plugins/toggle/mock_plugin", headers=secure_client_headers)
    response_json = response.json()

    assert response.status_code == 200
    assert "mock_plugin" in response_json["info"]

    # check directly the absence of the active plugin in the database
    assert "mock_plugin" not in crud_settings.get_setting_by_name(DEFAULT_SYSTEM_KEY, "active_plugins")["value"]
    assert "mock_plugin" not in crud_settings.get_setting_by_name(agent_id, "active_plugins")["value"]

    # the mock_plugin is no longer available into the cheshire cat
    _check_not_installed_in_cat(lizard, secure_client, secure_client_headers)

    # toggle plugin (reactivate) on a system level
    response = secure_client.put("/admins/plugins/toggle/mock_plugin", headers=secure_client_headers)
    response_json = response.json()

    assert response.status_code == 200
    assert "mock_plugin" in response_json["info"]

    # check directly the presence / absence of the active plugin in the database, for the system and the cheshirecat
    # respectively
    assert "mock_plugin" in crud_settings.get_setting_by_name(DEFAULT_SYSTEM_KEY, "active_plugins")["value"]
    assert "mock_plugin" not in crud_settings.get_setting_by_name(agent_id, "active_plugins")["value"]

    # the mock_plugin is available into the cheshire cat, but not active
    _check_installed_in_cat(secure_client, secure_client_headers, False)


def test_untoggle_base_plugin(lizard, secure_client, secure_client_headers):
    with pytest.raises(Exception):
        secure_client.put("/admins/plugins/toggle/base_plugin", headers=secure_client_headers)
