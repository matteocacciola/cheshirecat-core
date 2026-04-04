from cat.auth.permissions import get_full_permissions


async def test_get_available_permissions(client):
    response = await client.get("/auth/available-permissions")
    assert response.status_code == 200
    data = response.json()
    
    assert isinstance(data, dict)
    assert data == get_full_permissions()
