async def test_debug_client(client):
    assert not callable(client), "client is a function, not an instance!"