from cat.factory.agent import AgentOutput
from cat.mad_hatter.decorators import CatHook
from cat.memory.working_memory import CatMessage


def test_hook_discovery(plugin_manager):
    mock_plugin_hooks = plugin_manager.plugins["mock_plugin"].hooks

    assert len(mock_plugin_hooks) == 3
    for h in mock_plugin_hooks:
        assert isinstance(h, CatHook)
        assert h.plugin_id == "mock_plugin"


def test_hook_priority_execution(stray):
    fake_message = CatMessage(text="Priorities:")
    agent_output = AgentOutput()

    out = stray.plugin_manager.execute_hook("before_cat_sends_message", fake_message, agent_output, cat=None)
    assert out.content == "Priorities: priority 3 priority 2"
