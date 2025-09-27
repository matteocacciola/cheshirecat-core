import os
import pytest
from inspect import isfunction

import cat.utils as utils
from cat.mad_hatter import Plugin, CatProcedure
from cat.mad_hatter.decorators import CatHook, CatTool

from tests.utils import create_mock_plugin_zip


def test_instantiation_discovery(lizard):
    plugin_manager = lizard.plugin_manager
    all_plugins = plugin_manager.get_core_plugins_ids

    assert len(plugin_manager.plugins.keys()) == len(all_plugins)

    for k in plugin_manager.plugins.keys():
        assert k in all_plugins
        assert isinstance(plugin_manager.plugins[k], Plugin)

    loaded_plugins = plugin_manager.load_active_plugins_ids_from_db()
    for p in loaded_plugins:
        assert p in all_plugins
        assert plugin_manager.plugins[p].active

    # finds hooks
    assert len(plugin_manager.hooks.keys()) > 0
    for hook_name, hooks_list in plugin_manager.hooks.items():
        assert len(hooks_list) >= 1
        h = hooks_list[0]
        assert isinstance(h, CatHook)
        assert h.plugin_id in all_plugins
        assert isinstance(h.name, str)
        assert isfunction(h.function)
        assert h.priority >= 0.0

    # finds procedures
    assert len(plugin_manager.procedures_registry) == 3
    for procedure in plugin_manager.procedures_registry.values():
        assert isinstance(procedure, CatProcedure)
        if isinstance(procedure, CatTool):
            assert procedure.name in ["get_the_time", "get_weather", "read_working_memory"]
            assert procedure.description in [
                "Useful to get the current time when asked. Input is always None.",
                "Get the content of the Working Memory.",
                "Get the weather for a given city and date."
            ]
            assert isfunction(procedure.func)
            if procedure.name == "get_the_time":
                assert len(procedure.examples) == 2
                assert "what time is it" in procedure.examples
                assert "get the time" in procedure.examples
            elif procedure.name == "get_weather":
                assert len(procedure.examples) == 0
            elif procedure.name == "read_working_memory":
                assert len(procedure.examples) == 2
                assert "log working memory" in procedure.examples
                assert "show me the contents of working memory" in procedure.examples


# installation tests will be run for both flat and nested plugin
@pytest.mark.parametrize("plugin_is_flat", [True, False])
def test_plugin_install(lizard, plugin_is_flat):
    plugin_manager = lizard.plugin_manager
    core_plugins = plugin_manager.get_core_plugins_ids

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=plugin_is_flat)
    plugin_manager.install_plugin(new_plugin_zip_path)

    # archive extracted
    assert os.path.exists(os.path.join(utils.get_plugins_path(), "mock_plugin"))

    # plugins list updated
    assert "mock_plugin" in list(plugin_manager.plugins.keys())
    assert isinstance(plugin_manager.plugins["mock_plugin"], Plugin)
    assert (
        "mock_plugin" in plugin_manager.load_active_plugins_ids_from_db()
    )  # plugin starts active

    # plugin is activated by default
    assert len(plugin_manager.plugins["mock_plugin"].hooks) == 3
    assert len(plugin_manager.plugins["mock_plugin"].procedures) == 3
    assert len(plugin_manager.plugins["mock_plugin"].tools) == 1
    assert len(plugin_manager.plugins["mock_plugin"].forms) == 1
    assert len(plugin_manager.plugins["mock_plugin"].mcp_clients) == 1

    # tool found
    new_tool = plugin_manager.plugins["mock_plugin"].tools[0]
    assert new_tool.plugin_id == "mock_plugin"
    assert id(new_tool) == id(plugin_manager.procedures_registry["mock_tool"])  # cached and same object in memory!
    # tool examples found
    assert len(new_tool.examples) == 2
    assert "mock tool example 1" in new_tool.examples
    assert "mock tool example 2" in new_tool.examples

    # hooks found
    new_hooks = plugin_manager.plugins["mock_plugin"].hooks
    hooks_ram_addresses = []
    for h in new_hooks:
        assert h.plugin_id == "mock_plugin"
        hooks_ram_addresses.append(id(h))

    # found tool and hook have been cached
    mock_hook_name = "before_cat_sends_message"
    assert len(plugin_manager.hooks[mock_hook_name]) == 5  # 3 in cores, two in mock plugin
    expected_priorities = [3, 2, 1, 1, 0]
    for hook_idx, cached_hook in enumerate(plugin_manager.hooks[mock_hook_name]):
        assert cached_hook.name == mock_hook_name
        assert (
            cached_hook.priority == expected_priorities[hook_idx]
        )  # correctly sorted by priority
        if cached_hook.plugin_id not in core_plugins:
            assert cached_hook.plugin_id == "mock_plugin"
            assert id(cached_hook) in hooks_ram_addresses  # same object in memory!

    # list of active plugins in DB is correct
    active_plugins = plugin_manager.load_active_plugins_ids_from_db()
    assert len(active_plugins) == len(core_plugins) + 1
    assert "mock_plugin" in active_plugins


def test_plugin_uninstall_non_existent(lizard):
    plugin_manager = lizard.plugin_manager
    core_plugins = plugin_manager.get_core_plugins_ids

    # should not throw error
    assert len(plugin_manager.plugins) == len(core_plugins)
    plugin_manager.uninstall_plugin("wrong_plugin")
    assert len(plugin_manager.plugins) == len(core_plugins)

    # list of active plugins in DB is correct
    active_plugins = plugin_manager.load_active_plugins_ids_from_db()
    assert len(active_plugins) == len(core_plugins)
    for p in active_plugins:
        assert p in core_plugins


@pytest.mark.parametrize("plugin_is_flat", [True, False])
def test_plugin_uninstall(lizard, plugin_is_flat):
    plugin_manager = lizard.plugin_manager
    core_plugins = plugin_manager.get_core_plugins_ids

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=plugin_is_flat)
    plugin_manager.install_plugin(new_plugin_zip_path)

    # uninstall
    plugin_manager.uninstall_plugin("mock_plugin")

    # directory removed
    assert not os.path.exists(os.path.join(utils.get_plugins_path(), "mock_plugin"))

    # plugins list updated
    assert "mock_plugin" not in plugin_manager.plugins.keys()
    # plugin cache updated (only core plugins stuff)
    assert len(plugin_manager.hooks) > 0
    for h_name, h_list in plugin_manager.hooks.items():
        assert len(h_list) >= 1
        assert h_list[0].plugin_id in core_plugins
    assert len(plugin_manager.procedures_registry) == 3

    # list of active plugins in DB is correct
    active_plugins = plugin_manager.load_active_plugins_ids_from_db()
    assert len(active_plugins) == len(core_plugins)
    for p in active_plugins:
        assert p in core_plugins
