import shutil
import time
import uuid
import random
from urllib.parse import urlencode

from cat.db.cruds import users as crud_users
from cat.env import get_env
from cat.memory.utils import ContentType


agent_id = "agent_test"
api_key = "meow_http"
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
        # Send ws message
        websocket.send_json(msg)
        # get reply
        return websocket.receive_json()


# utility to send n messages via chat
def send_n_websocket_messages(num_messages, client, image=None):
    responses = []

    url = f"/ws/{agent_id}?" + urlencode({"token": api_key})

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


def get_fake_memory_export(embedder_name="DumbEmbedder", dim=2367):
    user = crud_users.get_user_by_username(agent_id, "user")
    return {
        "embedder": embedder_name,
        "collections": {
            "declarative": [
                {
                    "page_content": {
                        str(ContentType.TEXT): "test_memory"
                    },
                    "metadata": {"source": user["id"], "when": time.time()},
                    "id": str(uuid.uuid4()),
                    "vector": {
                        str(ContentType.TEXT): [random.random() for _ in range(dim)],
                        str(ContentType.IMAGE): [random.random() for _ in range(dim)],
                    }
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


def just_installed_plugin(client, headers, activate=False):
    # create zip file with a plugin
    zip_path = create_mock_plugin_zip(flat=True)
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin.zip in tests/mocks folder

    # upload plugin via endpoint
    with open(zip_path, "rb") as f:
        response = client.post(
            "/admins/plugins/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=headers
        )

    # request was processed
    assert response.status_code == 200
    assert response.json()["filename"] == zip_file_name

    if activate:
        # mock_plugin is installed but not enabled yet
        response = client.put("/plugins/toggle/mock_plugin", headers=headers)
        # request was processed
        assert response.status_code == 200
