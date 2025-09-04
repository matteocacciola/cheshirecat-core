import uuid
from qdrant_client.http.models import Filter, FieldCondition, MatchValue
import pytest

from cheshirecat.db.cruds import (
    settings as crud_settings,
    history as crud_history,
    plugins as crud_plugins,
    users as crud_users,
)
from cheshirecat.db.database import get_db
from cheshirecat.env import get_env
from cheshirecat.memory.utils import VectorMemoryCollectionTypes

from tests.utils import create_new_user, get_client_admin_headers, new_user_password


@pytest.mark.asyncio
async def test_factory_reset_success(client, lizard, cheshire_cat):
    # check that the vector database is not empty
    c = await cheshire_cat.vector_memory_handler._client.get_collections()
    assert len(c.collections) > 0

    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/factory/reset", headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": True, "deleted_memories": True, "deleted_plugin_folders": True}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) == 0

    # check that the Lizard has been correctly recreated from scratch
    settings = crud_settings.get_settings(lizard.config_key)
    assert len(settings) > 0

    # check that the vector database is not empty
    c = await cheshire_cat.vector_memory_handler._client.get_collections()
    assert len(c.collections) == 1

    histories = get_db().get(crud_history.format_key(cheshire_cat.id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(cheshire_cat.id, "*"))
    assert plugins is None

    users = get_db().get(crud_users.format_key(cheshire_cat.id))
    assert users is None


@pytest.mark.asyncio
async def test_agent_destroy_success(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent/destroy", headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": True, "deleted_memories": True, "deleted_plugin_folders": False}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) == 0

    histories = get_db().get(crud_history.format_key(cheshire_cat.id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(cheshire_cat.id, "*"))
    assert plugins is None

    users = get_db().get(crud_users.format_key(cheshire_cat.id))
    assert users is None

    qdrant_filter = Filter(must=[FieldCondition(key="tenant_id", match=MatchValue(value=cheshire_cat.id))])
    for c in VectorMemoryCollectionTypes:
        count_response = await cheshire_cat.vector_memory_handler._client.count(
            collection_name=str(c), count_filter=qdrant_filter
        )
        assert count_response.count == 0


@pytest.mark.asyncio
async def test_agent_reset_success(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent/reset", headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": True, "deleted_memories": True, "deleted_plugin_folders": False}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0

    histories = get_db().get(crud_history.format_key(cheshire_cat.id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(cheshire_cat.id, "*"))
    assert plugins is None

    users = crud_users.get_users(cheshire_cat.id)
    assert len(users) == 1

    ccat = lizard.get_cheshire_cat(cheshire_cat.id)
    for c in VectorMemoryCollectionTypes:
        num_vectors = await ccat.vector_memory_handler.get_vectors_count(str(c))
        points, _ = await ccat.vector_memory_handler.get_all_points(str(c))
        assert num_vectors == 0
        assert len(points) == 0


@pytest.mark.asyncio
async def test_agent_destroy_error_because_of_lack_of_permissions(client, lizard, cheshire_cat):
    # create new admin with wrong permissions
    data = create_new_user(
        client, "/admins/users", headers=get_client_admin_headers(client), permissions={"EMBEDDER": ["READ"]}
    )

    creds = {"username": data["username"], "password": new_user_password}
    res = client.post("/admins/auth/token", json=creds)
    received_token = res.json()["access_token"]

    response = client.post(
        "/admins/utils/agent/destroy",
        headers={"Authorization": f"Bearer {received_token}", "agent_id": cheshire_cat.id}
    )

    assert response.status_code == 403

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0

    collections = await cheshire_cat.vector_memory_handler._client.get_collections()
    assert len(collections.collections) > 0

    for c in VectorMemoryCollectionTypes:
        num_vectors = await cheshire_cat.vector_memory_handler.get_vectors_count(str(c))
        points, _ = await cheshire_cat.vector_memory_handler.get_all_points(str(c))
        assert num_vectors == 0
        assert len(points) == 0


@pytest.mark.asyncio
async def test_agent_destroy_error_because_of_not_existing_agent(client, lizard, cheshire_cat):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent/destroy", headers={"Authorization": f"Bearer {received_token}", "agent_id": "wrong_id"}
    )

    assert response.status_code == 200
    assert response.json() == {"deleted_settings": False, "deleted_memories": False, "deleted_plugin_folders": False}

    settings = crud_settings.get_settings(cheshire_cat.id)
    assert len(settings) > 0

    collections = await cheshire_cat.vector_memory_handler._client.get_collections()
    assert len(collections.collections) > 0

    for c in VectorMemoryCollectionTypes:
        num_vectors = await cheshire_cat.vector_memory_handler.get_vectors_count(str(c))
        points, _ = await cheshire_cat.vector_memory_handler.get_all_points(str(c))
        assert num_vectors == 0
        assert len(points) == 0


@pytest.mark.asyncio
async def test_agent_create_success(client, lizard):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    new_agent_id = str(uuid.uuid4())

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200

    received_token = res.json()["access_token"]
    response = client.post(
        "/admins/utils/agent/create", headers={"Authorization": f"Bearer {received_token}", "agent_id": new_agent_id}
    )

    assert response.status_code == 200
    assert response.json() == {"created": True}

    settings = crud_settings.get_settings(new_agent_id)
    assert len(settings) > 0

    histories = get_db().get(crud_history.format_key(new_agent_id, "*"))
    assert histories is None

    plugins = get_db().get(crud_plugins.format_key(new_agent_id, "*"))
    assert plugins is None

    users = crud_users.get_users(new_agent_id)
    assert len(users) == 1

    ccat = lizard.get_cheshire_cat(new_agent_id)
    for c in VectorMemoryCollectionTypes:
        num_vectors = await ccat.vector_memory_handler.get_vectors_count(str(c))
        points, _ = await ccat.vector_memory_handler.get_all_points(str(c))
        assert num_vectors == 0
        assert len(points) == 0