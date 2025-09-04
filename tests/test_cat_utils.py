import os
import pytest

from cat import utils

from tests.utils import agent_id


def test_get_base_url():
    assert utils.get_base_url() == "http://localhost:1865/"
     # test when CCAT_CORE_USE_SECURE_PROTOCOLS is set
    os.environ["CCAT_CORE_USE_SECURE_PROTOCOLS"] = "1"
    assert utils.get_base_url() == "https://localhost:1865/"
    os.environ["CCAT_CORE_USE_SECURE_PROTOCOLS"] = "0"
    assert utils.get_base_url() == "http://localhost:1865/"
    os.environ["CCAT_CORE_USE_SECURE_PROTOCOLS"] = ""
    assert utils.get_base_url() == "http://localhost:1865/"


def test_get_base_path():
    assert utils.get_base_path() == "/app/cat/"


def test_get_plugin_path():
    # plugin folder is "cat/plugins/" in production, "tests/mocks/mock_plugin_folder/" during tests
    assert utils.get_plugins_path() == "tests/mocks/mock_plugin_folder/"


def test_get_data_path(client):
    assert utils.get_data_path() == os.path.join(utils.get_project_path(), "data")


def test_get_static_path(client):
    assert utils.get_static_path() == os.path.join(utils.get_project_path(), "static")


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
        utils.parse_json(invalid_json) == expected_json
    assert "substring not found" in str(e.value)


# BaseModelDict to be deprecated in v2
def test_base_dict_model():
    class Origin(utils.BaseModelDict):
        location: str

    class Cat(utils.BaseModelDict):
        color: str
        origin: Origin

    origin = Origin(location="Cheshire")

    cat = Cat(color="pink", origin=origin)
    assert cat["color"] == cat.color == "pink"

    accesses = {"Cheshire", cat.origin.location, cat.origin["location"], cat["origin"].location,
                cat["origin"]["location"], cat.get("origin").get("location")}
    assert len(accesses) == 1

    # edit custom attributes
    cat.something = "meow"
    cat.origin.something = "meow"
    accesses = {"meow", cat.something, cat["something"], cat.origin.something, cat["origin"]["something"],
                cat["origin"].something, cat.get("origin").get("something"), cat.get("missing", "meow"),
                cat.origin.get("missing", "meow")}
    assert len(accesses) == 1

    # .keys()
    assert set(cat.keys()) == {"color", "origin", "something"}
    assert set(cat.origin.keys()) == {"location", "something"}
    assert set(cat.origin.values()) == {"Cheshire", "meow"}

    # in
    assert "color" in cat
    assert "location" in cat.origin


def test_load_settings_raise_exception(stray_no_memory):
    with pytest.raises(Exception) as e:
        stray_no_memory.mad_hatter.get_plugin()
        assert e == "get_plugin() can only be called from within a plugin"


def test_load_settings_no_agent_key_from_stray_cat(stray_no_memory):
    original_fnc = utils.inspect_calling_folder
    utils.inspect_calling_folder = lambda: "base_plugin"

    plugin_manager = stray_no_memory.mad_hatter
    plugin = plugin_manager.get_plugin()
    plugin.load_settings()
    assert utils.inspect_calling_agent().id == agent_id

    utils.inspect_calling_folder = original_fnc


def test_load_settings_no_agent_key_from_stray_cat_long(stray_no_memory):
    original_fnc = utils.inspect_calling_folder
    utils.inspect_calling_folder = lambda: "base_plugin"

    stray_no_memory.mad_hatter.get_plugin().load_settings()
    assert utils.inspect_calling_agent().id == agent_id

    utils.inspect_calling_folder = original_fnc


def test_load_settings_no_agent_key_from_cheshire_cat(cheshire_cat):
    original_fnc = utils.inspect_calling_folder
    utils.inspect_calling_folder = lambda: "base_plugin"

    plugin_manager = cheshire_cat.mad_hatter
    plugin = plugin_manager.get_plugin()
    plugin.load_settings()

    assert utils.inspect_calling_agent().id == agent_id

    utils.inspect_calling_folder = original_fnc


def test_load_settings_no_agent_key_from_cheshire_cat_long(cheshire_cat):
    original_fnc = utils.inspect_calling_folder
    utils.inspect_calling_folder = lambda: "base_plugin"

    cheshire_cat.mad_hatter.get_plugin().load_settings()

    assert utils.inspect_calling_agent().id == agent_id

    utils.inspect_calling_folder = original_fnc