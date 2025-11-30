import os
import pytest

from cat import utils

from tests.utils import agent_id


def test_get_base_path():
    assert utils.get_base_path() == "/app/cat/"


def test_get_plugin_path():
    # plugin folder is "cat/plugins/" in production, "tests/mocks/mock_plugin_folder/" during tests
    assert utils.get_plugins_path() == "tests/mocks/mock_plugin_folder/"


def test_get_data_path(client):
    assert utils.get_data_path() == os.path.join(utils.get_project_path(), "data")


def test_levenshtein_distance():
    assert utils.levenshtein_distance("hello world", "hello world") == 0.0
    assert utils.levenshtein_distance("hello world", "") == 1.0


def test_parse_json():
    json_string = """{
    "a": 2
}"""

    expected_json = {"a": 2}

    prefixed_json = "anything \n\t```json\n" + json_string
    assert utils.parse_json(prefixed_json) == expected_json

    suffixed_json = json_string + "\n``` anything"
    assert utils.parse_json(suffixed_json) == expected_json

    unclosed_json = """{"a":2"""
    assert utils.parse_json(unclosed_json) == expected_json

    unclosed_key_json = """{"a":2, "b":"""
    assert utils.parse_json(unclosed_key_json) == expected_json

    invalid_json = """yaml is better"""
    with pytest.raises(Exception) as e:
        utils.parse_json(invalid_json)
    assert "substring not found" in str(e.value)


def test_load_settings_raise_exception(stray_no_memory):
    with pytest.raises(Exception) as e:
        stray_no_memory.plugin_manager.get_plugin()
        assert e == "get_plugin() can only be called from within a plugin"


def test_load_settings_no_agent_key_from_stray_cat(stray_no_memory):
    original_fnc = utils.inspect_calling_folder
    utils.inspect_calling_folder = lambda: "base_plugin"

    stray_no_memory.plugin_manager.get_plugin().load_settings()
    assert utils.inspect_calling_agent().agent_key == agent_id

    utils.inspect_calling_folder = original_fnc


def test_load_settings_no_agent_key_from_cheshire_cat(cheshire_cat):
    original_fnc = utils.inspect_calling_folder
    utils.inspect_calling_folder = lambda: "base_plugin"

    cheshire_cat.plugin_manager.get_plugin().load_settings()
    assert utils.inspect_calling_agent().agent_key == agent_id

    utils.inspect_calling_folder = original_fnc
