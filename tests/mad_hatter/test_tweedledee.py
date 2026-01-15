from inspect import isfunction

from cat.looking_glass.mad_hatter.decorators.hook import CatHook
from cat.looking_glass.mad_hatter.decorators.tool import CatTool
from cat.looking_glass.mad_hatter.plugin import Plugin
from cat.looking_glass.mad_hatter.procedures import CatProcedure


def test_instantiation_discovery(cheshire_cat):
    plugin_manager = cheshire_cat.plugin_manager
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

    # finds tool
    assert len(plugin_manager.procedures_registry) == 2
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
