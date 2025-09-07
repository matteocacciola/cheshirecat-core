from inspect import isfunction

from cat.mad_hatter import Plugin
from cat.mad_hatter.decorators import CatHook, CatTool

def test_instantiation_discovery(cheshire_cat):
    plugin_manager = cheshire_cat.plugin_manager
    all_plugins = plugin_manager.get_core_plugins_ids()

    assert len(plugin_manager.plugins.keys()) == len(all_plugins)
    
    for k in plugin_manager.plugins.keys():
        assert k in all_plugins
        assert isinstance(plugin_manager.plugins[k], Plugin)

    loaded_plugins = plugin_manager.load_active_plugins_from_db()
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
    assert len(plugin_manager.tools) == 3
    for tool in plugin_manager.tools:
        assert isinstance(tool, CatTool)
        assert tool.name in ["get_the_time", "read_working_memory", "get_weather"]
        assert tool.description in [
            "Useful to get the current time when asked. Input is always None.",
            "Get the content of the Working Memory.",
            "Get the weather for a given city and date."
        ]
        assert isfunction(tool.func)
        if tool.name == "get_the_time":
            assert len(tool.start_examples) == 2
            assert "what time is it" in tool.start_examples
            assert "get the time" in tool.start_examples
        elif tool.name == "read_working_memory":
            assert len(tool.start_examples) == 2
            assert "log working memory" in tool.start_examples
            assert "show me the contents of working memory" in tool.start_examples
        elif tool.name == "get_weather":
            assert len(tool.start_examples) == 0
