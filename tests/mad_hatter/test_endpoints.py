from cheshirecat.mad_hatter.decorators import CustomEndpoint


def get_endpoint(plugin_manager, uri, method=None):
    for e in plugin_manager.endpoints:
        condition = e.name == uri
        if method:
            condition = condition and method in e.methods
        if condition:
            return e

    return None


def test_endpoints_discovery(plugin_manager):
    mock_plugin_endpoints = plugin_manager.plugins["mock_plugin"].endpoints
    assert mock_plugin_endpoints == plugin_manager.endpoints

    # discovered endpoints
    assert len(mock_plugin_endpoints) == 7

    # basic properties
    for e in mock_plugin_endpoints:
        assert isinstance(e, CustomEndpoint)
        assert e.plugin_id == "mock_plugin"


def test_endpoint_decorator(plugin_manager):
    endpoint = get_endpoint(plugin_manager, "/custom/endpoint")

    assert endpoint.name == "/custom/endpoint"
    assert endpoint.prefix == "/custom"
    assert endpoint.path == "/endpoint"
    assert endpoint.methods == {"GET"}  # fastapi stores http verbs as a set
    assert endpoint.tags == ["Custom Endpoints"]
    assert endpoint.function() == {"result": "endpoint default prefix"}


def test_endpoint_decorator_prefix(plugin_manager):
    endpoint = get_endpoint(plugin_manager, "/tests/endpoint")

    assert endpoint.name == "/tests/endpoint"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/endpoint"
    assert endpoint.methods == {"GET"}
    assert endpoint.tags == ["Tests"]
    assert endpoint.function() == {"result": "endpoint prefix tests"}


def test_get_endpoint(plugin_manager):
    endpoint = get_endpoint(plugin_manager, "/tests/crud", "GET")

    assert endpoint.name == "/tests/crud"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/crud"
    assert endpoint.methods == {"GET"}
    assert endpoint.tags == ["Tests"]


def test_post_endpoint(plugin_manager):
    endpoint = get_endpoint(plugin_manager, "/tests/crud", "POST")

    assert endpoint.name == "/tests/crud"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/crud"
    assert endpoint.methods == {"POST"}
    assert endpoint.tags == ["Tests"]


def test_put_endpoint(plugin_manager):
    endpoint = get_endpoint(plugin_manager, "/tests/crud/{item_id}", "PUT")

    assert endpoint.name == "/tests/crud/{item_id}"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/crud/{item_id}"
    assert endpoint.methods == {"PUT"}
    assert endpoint.tags == ["Tests"]


def test_delete_endpoint(plugin_manager):
    endpoint = get_endpoint(plugin_manager, "/tests/crud/{item_id}", "DELETE")

    assert endpoint.name == "/tests/crud/{item_id}"
    assert endpoint.prefix == "/tests"
    assert endpoint.path == "/crud/{item_id}"
    assert endpoint.methods == {"DELETE"}
    assert endpoint.tags == ["Tests"]


def test_endpoints_deactivation_or_uninstall(plugin_manager):
    # custom endpoints are registered in mad_hatter
    for e in plugin_manager.endpoints:
        assert isinstance(e, CustomEndpoint)
        assert e.plugin_id == "mock_plugin"

    plugin_manager.uninstall_plugin("mock_plugin")

    # no more custom endpoints
    assert plugin_manager.endpoints == []
