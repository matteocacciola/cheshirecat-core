from cat.mad_hatter.decorators import CustomEndpoint

from tests.mocks.mock_plugin.mock_endpoint import Item


def test_endpoints_discovery(plugin_manager):
    mock_plugin_endpoints = plugin_manager.plugins["mock_plugin"].endpoints
    assert mock_plugin_endpoints == plugin_manager.endpoints

    # discovered endpoints
    assert len(mock_plugin_endpoints) == 6

    # basic properties
    for e in mock_plugin_endpoints:
        assert isinstance(e, CustomEndpoint)
        assert e.plugin_id == "mock_plugin"


def test_endpoint_decorator(plugin_manager):
    endpoint = plugin_manager.endpoints[1]

    assert endpoint.name == "/custom/endpoint"
    assert endpoint.prefix == "/custom"
    assert endpoint.path == "/endpoint"
    assert endpoint.methods == {"GET"}  # fastapi stores http verbs as a set
    assert endpoint.tags == ["Custom Endpoints"]
    assert endpoint.function() == {"result": "endpoint default prefix"}


def test_endpoint_decorator_prefix(plugin_manager):
    endpoint = plugin_manager.endpoints[2]

    assert endpoint.name == "/tests/endpoint"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/endpoint"
    assert endpoint.methods == {"GET"}
    assert endpoint.tags == ["Tests"]
    assert endpoint.function() == {"result": "endpoint prefix tests"}


def test_get_endpoint(plugin_manager):
    endpoint = plugin_manager.endpoints[3]

    assert endpoint.name == "/tests/crud"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/crud"
    assert endpoint.methods == {"GET"}
    assert endpoint.tags == ["Tests"]
    # too complicated to simulate the request arguments here,
    #  see tests/routes/test_custom_endpoints.py


def test_post_endpoint(plugin_manager):
    endpoint = plugin_manager.endpoints[4]

    assert endpoint.name == "/tests/crud"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/crud"
    assert endpoint.methods == {"POST"}
    assert endpoint.tags == ["Tests"]

    payload = Item(name="the cat", description="it's magic")
    assert endpoint.function(payload) == payload.model_dump()


def test_put_endpoint(plugin_manager):
    endpoint = plugin_manager.endpoints[5]

    assert endpoint.name == "/tests/crud"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/crud"
    assert endpoint.methods == {"PUT"}
    assert endpoint.tags == ["Tests"]

    payload = Item(name="the cat", description="it's magic")
    assert endpoint.function(payload) == payload.model_dump()


def test_delete_endpoint(plugin_manager):
    endpoint = plugin_manager.endpoints[0]

    assert endpoint.name == "/tests/crud"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/crud"
    assert endpoint.methods == {"DELETE"}
    assert endpoint.tags == ["Tests"]

    payload = Item(name="the cat", description="it's magic")
    assert endpoint.function(payload) == payload.model_dump()


def test_endpoints_deactivation_or_uninstall(plugin_manager):
    # custom endpoints are registered in mad_hatter
    for e in plugin_manager.endpoints:
        assert isinstance(e, CustomEndpoint)
        assert e.plugin_id == "mock_plugin"

    plugin_manager.uninstall_plugin("mock_plugin")

    # no more custom endpoints
    assert plugin_manager.endpoints == []
