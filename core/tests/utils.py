import asyncio
import shutil
import time
import uuid
import random
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor

from cat.db.cruds import users as crud_users
from cat.env import get_env

agent_id = "agent_test"
api_key = "meow_http"
api_key_ws = "meow_ws"
jwt_secret = "meow_jwt"

new_user_password = "wandering_in_wonderland"
mock_plugin_path = "tests/mocks/mock_plugin/"

fake_timestamp = 1705855981


def get_class_from_decorated_singleton(singleton):
    return singleton().__class__


# utility function to communicate with the cat via websocket
def send_websocket_message(msg, client, query_params):
    url = f"/ws/{agent_id}?" + urlencode(query_params)

    with client.websocket_connect(url) as websocket:
        # sed ws message
        websocket.send_json(msg)
        # get reply
        reply = websocket.receive_json()

    return reply


# utility to send n messages via chat
def send_n_websocket_messages(num_messages, client, image=None):
    responses = []

    url = f"/ws/{agent_id}?" + urlencode({"token": api_key_ws})

    with client.websocket_connect(url) as websocket:
        for m in range(num_messages):
            message = {"text": f"Red Queen {m}"}
            if image:
                message["image"] = image
            # sed ws message
            websocket.send_json(message)
            # get reply
            reply = websocket.receive_json()
            responses.append(reply)

    return responses


def key_in_json(key, json):
    return key in json.keys()


# create a plugin zip out of the mock plugin folder.
# - Used to test plugin upload.
# - zip can be created flat (plugin files in root dir) or nested (plugin files in zipped folder)
def create_mock_plugin_zip(flat: bool, plugin_id="mock_plugin"):
    if flat:
        root_dir = f"tests/mocks/{plugin_id}"
        base_dir = "./"
    else:
        root_dir = "tests/mocks/"
        base_dir = plugin_id

    return shutil.make_archive(
        base_name=f"tests/mocks/{plugin_id}",
        format="zip",
        root_dir=root_dir,
        base_dir=base_dir,
    )


# utility to retrieve embedded tools from endpoint
def get_procedural_memory_contents(client, params=None, headers=None):
    headers = headers or {} | {"agent_id": agent_id}
    final_params = (params or {}) | {"text": "random"}
    response = client.get("/memory/recall/", params=final_params, headers=headers)
    json = response.json()
    return json["vectors"]["collections"]["procedural"]


# utility to retrieve declarative memory contents
def get_declarative_memory_contents(client, headers=None):
    headers = headers or {} | {"agent_id": agent_id}
    params = {"text": "Something"}
    response = client.get("/memory/recall/", params=params, headers=headers)
    assert response.status_code == 200
    json = response.json()
    declarative_memories = json["vectors"]["collections"]["declarative"]
    return declarative_memories


# utility to get collections and point count from `GET /memory/collections` in a simpler format
def get_collections_names_and_point_count(client, headers=None):
    headers = headers or {} | {"agent_id": agent_id}
    response = client.get("/memory/collections", headers=headers)
    json = response.json()
    assert response.status_code == 200
    collections_n_points = {c["name"]: c["vectors_count"] for c in json["collections"]}
    return collections_n_points


def create_new_user(client, route: str, username="Alice", headers=None, permissions=None):
    new_user = {"username": username, "password": new_user_password}
    if permissions:
        new_user["permissions"] = permissions
    response = client.post(route, json=new_user, headers=headers)
    assert response.status_code == 200
    return response.json()


def check_user_fields(u):
    assert set(u.keys()) == {"id", "username", "permissions"}
    assert isinstance(u["username"], str)
    assert isinstance(u["permissions"], dict)
    try:
        # Attempt to create a UUID object from the string to validate it
        uuid_obj = uuid.UUID(u["id"], version=4)
        assert str(uuid_obj) == u["id"]
    except ValueError:
        # If a ValueError is raised, the UUID string is invalid
        assert False, "Not a UUID"


def run_in_thread(fnc, *args):
    """
    Helper function to run functions in a separate thread.
    """

    with ThreadPoolExecutor() as executor:
        future = executor.submit(fnc, *args)
        return future.result()


async def async_run(loop, fnc, *args):
    """
    Asynchronously run a function (sync or async) in a separate thread.
    """

    if asyncio.iscoroutinefunction(fnc):
        return await fnc(*args)

    return await loop.run_in_executor(None, run_in_thread, fnc, *args)


def get_fake_memory_export(embedder_name="DumbEmbedder", dim=2367):
    user = crud_users.get_user_by_username(agent_id, "user")
    return {
        "embedder": embedder_name,
        "collections": {
            "declarative": [
                {
                    "page_content": "test_memory",
                    "metadata": {"source": user["id"], "when": time.time()},
                    "id": str(uuid.uuid4()),
                    "vector": [random.random() for _ in range(dim)],
                }
            ]
        },
    }


def get_client_admin_headers(client):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/admins/auth/token", json=creds)
    assert res.status_code == 200
    token = res.json()["access_token"]

    return {"Authorization": f"Bearer {token}"}


def mock_plugin_settings_file(file_path: str | None = "tests/mocks/mock_plugin/settings.py"):
    content = '''
from pydantic import BaseModel

from cat.mad_hatter.decorators import plugin


class MockSettings(BaseModel):
    existing_key: str = "new_value"


@plugin
def settings_model():
    return MockSettings
    '''

    with open(file_path, "w") as file:
        file.write(content)
