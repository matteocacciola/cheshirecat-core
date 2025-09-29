def test_ping_success(client):
    response = client.get("/")
    assert response.status_code == 200

    json_response = response.json()
    assert "status" in json_response
    assert "entities" in json_response
    assert len(json_response["entities"]) >= 2
