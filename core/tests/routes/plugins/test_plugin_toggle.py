from tests.utils import get_procedural_memory_contents, just_installed_plugin


def check_active_plugin_properties(plugin):
    assert plugin["id"] == "mock_plugin"
    assert len(plugin["hooks"]) == 3
    assert len(plugin["tools"]) == 1
    assert len(plugin["forms"]) == 1


def check_inactive_plugin_properties(plugin):
    assert plugin["id"] == "mock_plugin"
    assert len(plugin["hooks"]) == 0
    assert len(plugin["tools"]) == 0
    assert len(plugin["forms"]) == 0


def test_toggle_non_existent_plugin(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    response = secure_client.put("/plugins/toggle/no_plugin", headers=secure_client_headers)
    response_json = response.json()

    assert response.status_code == 404
    assert response_json["detail"]["error"] == "Plugin not found"


def test_activate_plugin(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    # activate
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # GET plugins endpoint lists the plugin
    response = secure_client.get("/plugins", headers=secure_client_headers)
    installed_plugins = response.json()["installed"]
    mock_plugin = [p for p in installed_plugins if p["id"] == "mock_plugin"][0]
    assert isinstance(mock_plugin["active"], bool)
    assert mock_plugin["active"]  # plugin active
    check_active_plugin_properties(mock_plugin)

    # check whether procedures have been embedded
    procedures = get_procedural_memory_contents(secure_client, headers=secure_client_headers)
    assert len(procedures) == 9  # two tools, 4 tools examples, 3  form triggers
    procedures_names = list(map(lambda t: t["metadata"]["source"], procedures))
    assert procedures_names.count("mock_tool") == 3
    assert procedures_names.count("get_the_time") == 3
    assert procedures_names.count("PizzaForm") == 3

    procedures_sources = list(map(lambda t: t["metadata"]["type"], procedures))
    assert procedures_sources.count("tool") == 6
    assert procedures_sources.count("form") == 3

    procedures_triggers = list(map(lambda t: t["metadata"]["trigger_type"], procedures))
    assert procedures_triggers.count("start_example") == 6
    assert procedures_triggers.count("description") == 3


def test_deactivate_plugin(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    # activate
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # deactivate
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # GET plugins endpoint lists the plugin
    response = secure_client.get("/plugins", headers=secure_client_headers)
    installed_plugins = response.json()["installed"]
    assert len(installed_plugins) == 2  # core_plugin and mock_plugin

    mock_plugin = [p for p in installed_plugins if p["id"] == "mock_plugin"][0]
    assert isinstance(mock_plugin["active"], bool)
    assert not mock_plugin["active"]  # plugin NOT active
    check_inactive_plugin_properties(mock_plugin)

    # tool has been taken away
    procedures = get_procedural_memory_contents(secure_client, headers=secure_client_headers)
    assert len(procedures) == 3
    procedures_sources = list(map(lambda t: t["metadata"]["source"], procedures))
    assert "mock_tool" not in procedures_sources
    assert "PizzaForm" not in procedures_sources
    assert "get_the_time" in procedures_sources  # from core_plugin

    # only examples for core tool
    procedures_types = list(map(lambda t: t["metadata"]["type"], procedures))
    assert procedures_types.count("tool") == 3
    assert procedures_types.count("form") == 0
    procedures_triggers = list(map(lambda t: t["metadata"]["trigger_type"], procedures))
    assert procedures_triggers.count("start_example") == 2
    assert procedures_triggers.count("description") == 1


def test_reactivate_plugin(secure_client, secure_client_headers):
    just_installed_plugin(secure_client, secure_client_headers)

    # activate
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # deactivate
    secure_client.put("/plugins/toggle/mock_plugin", headers=secure_client_headers)

    # re-activate
    test_activate_plugin(secure_client, secure_client_headers)
