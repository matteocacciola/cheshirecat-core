from uuid import uuid4
import pytest
import pytest_asyncio
import os
import shutil
import warnings
from asgi_lifespan import LifespanManager
from httpx import AsyncClient, ASGITransport
from pydantic import PydanticDeprecatedSince20
from qdrant_client import AsyncQdrantClient
import time

from cat.auth import auth_utils
from cat.auth.permissions import AuthUserInfo, get_base_permissions
from cat.env import get_env
from cat.looking_glass import StrayCat
from cat.looking_glass.mad_hatter.plugin import Plugin
from cat.startup import grinning_cat_api
from cat.services.memory.messages import UserMessage
from cat.services.factory.vector_db import QdrantHandler
import cat.utils as utils

from tests.utils import (
    agent_id,
    api_key,
    jwt_secret,
    create_mock_plugin_zip,
    mock_plugin_path,
    fake_timestamp,
)

pytest_plugins = ["pytest_asyncio"]

memory_client = AsyncQdrantClient(":memory:")

# substitute classes' methods where necessary for testing purposes
def mock_classes(monkeypatch):
    # Mock the entire __init__ method to set _client to memory client, and the close method to do nothing
    def mock_init_vector_database(self, *args, **kwargs):
        # Call the parent __init__
        super(QdrantHandler, self).__init__()
        # Set the _client to memory client
        self._client = memory_client
        self.save_memory_snapshots = kwargs.get("save_memory_snapshots", False)
    monkeypatch.setattr(QdrantHandler, "__init__", mock_init_vector_database)
    monkeypatch.setattr(QdrantHandler, "close", lambda self: None)

    utils.get_plugins_path = lambda: "tests/mocks/mock_plugin_folder/"
    utils.get_file_manager_root_storage_path = lambda: "tests/data/storage"

    # do not check plugin dependencies at every restart
    def mock_install_requirements(self):
        pass
    monkeypatch.setattr(Plugin, "_install_requirements", mock_install_requirements)

    # mock the agent_id in the request
    auth_utils.extract_agent_id_from_request = lambda: agent_id


async def clean_up():
    from cat.db.database import get_sync_db

    # clean up service files and mocks
    to_be_removed = [
        "tests/mocks/mock_plugin.zip",
        "tests/mocks/mock_plugin_fast_reply.zip",
        "tests/mocks/mock_plugin_multimodal_embedder.zip",
        "tests/mocks/mock_plugin_with_dependencies.zip",
        "tests/mocks/mock_plugin/settings.json",
        "tests/mocks/mock_plugin_folder/mock_plugin",
        "tests/mocks/mock_plugin_folder/mock_plugin_fast_reply",
        "tests/mocks/mock_plugin_folder/mock_plugin_multimodal_embedder",
        "tests/mocks/mock_plugin_folder/mock_plugin_with_dependencies",
        "tests/mocks/empty_folder",
        "tests/data",
    ]
    for tbr in to_be_removed:
        if os.path.exists(tbr):
            if os.path.isdir(tbr):
                shutil.rmtree(tbr)
            else:
                os.remove(tbr)

    # flush redis database
    get_sync_db().flushdb()

    # delete all the collections in Qdrant
    collections = await memory_client.get_collections()
    for collection in collections.collections:
        await memory_client.delete_collection(collection.name)

    # delete all singletons!!!
    utils.singleton.instances.clear()


def should_skip_encapsulation(request):
    return request.node.get_closest_marker("skip_encapsulation") is not None


@pytest_asyncio.fixture(autouse=True)
async def encapsulate_each_test(request, monkeypatch):
    from cat.db.database import Database

    if should_skip_encapsulation(request):
        yield
        return

    mock_classes(monkeypatch)

    current_debug = get_env("CAT_DEBUG")
    current_redis_db = get_env("CAT_REDIS_DB")
    os.environ["CAT_DEBUG"] = "false"
    os.environ["CAT_REDIS_DB"] = "1"

    await clean_up()
    yield
    await clean_up()

    Database().reset_async()

    if current_debug:
        os.environ["CAT_DEBUG"] = current_debug
    else:
        del os.environ["CAT_DEBUG"]
    if current_redis_db:
        os.environ["CAT_REDIS_DB"] = current_redis_db
    else:
        del os.environ["CAT_REDIS_DB"]


@pytest_asyncio.fixture(scope="function")
async def client():
    async with LifespanManager(grinning_cat_api) as manager:
        async with AsyncClient(transport=ASGITransport(app=manager.app), base_url="http://test") as ac:
            yield ac


# This fixture sets the CAT_API_KEY environment variable,
# making mandatory for clients to possess api key or JWT
@pytest_asyncio.fixture(scope="function")
async def secure_client(client):
    current_api_key = os.getenv("CAT_API_KEY")
    current_jwt_secret = os.getenv("CAT_JWT_SECRET")

    # set ENV variables
    os.environ["CAT_API_KEY"] = api_key
    os.environ["CAT_JWT_SECRET"] = jwt_secret

    yield client

    # clean up
    if current_api_key:
        os.environ["CAT_API_KEY"] = current_api_key
    else:
        del os.environ["CAT_API_KEY"]
    if current_jwt_secret:
        os.environ["CAT_JWT_SECRET"] = current_jwt_secret
    else:
        del os.environ["CAT_JWT_SECRET"]


@pytest.fixture(scope="function")
def secure_client_headers():
    yield {"X-Agent-ID": agent_id, "Authorization": f"Bearer {api_key}"}


@pytest.fixture(scope="function")
def lizard(client):
    yield grinning_cat_api.state.lizard


@pytest_asyncio.fixture(scope="function")
async def cheshire_cat(lizard):
    cheshire_cat = await lizard.create_cheshire_cat(agent_id)
    yield cheshire_cat


@pytest_asyncio.fixture(scope="function")
async def plugin_manager(lizard):
    plugin_manager = lizard.plugin_manager

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    await lizard.install_plugin(new_plugin_zip_path)

    yield plugin_manager

    await plugin_manager.uninstall_plugin("mock_plugin")


@pytest_asyncio.fixture(scope="function")
async def agent_plugin_manager(cheshire_cat):
    plugin_manager = cheshire_cat.plugin_manager

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    plugin_id = await cheshire_cat.lizard.install_plugin(new_plugin_zip_path)

    # activate the plugin within the Cheshire Cat whose plugin manager is being used
    await cheshire_cat.toggle_plugin(plugin_id)

    yield plugin_manager


@pytest_asyncio.fixture(scope="function")
async def stray_no_memory(cheshire_cat, agent_plugin_manager):
    stray_cat = await StrayCat.create(
        user_data=AuthUserInfo(id=str(uuid4()), name="Alice", permissions=get_base_permissions()),
        agent_id=cheshire_cat.agent_key,
        plugin_manager_generator=lambda: agent_plugin_manager,
    )
    yield stray_cat


# fixture to have available an instance of StrayCat
@pytest_asyncio.fixture(scope="function")
async def stray(stray_no_memory):
    stray_no_memory.working_memory.user_message = UserMessage(text="meow")
    yield stray_no_memory


# auto-use fixture will be applied to *all* the tests
@pytest.fixture(autouse=True, scope="function")
def apply_warning_filters():
    # ignore deprecation warnings due to langchain not updating to pydantic v2
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)


#fixture for mock time.time function
@pytest.fixture(scope="function")
def patch_time_now(monkeypatch):
    def my_time():
        return fake_timestamp

    monkeypatch.setattr(time, "time", my_time)


# this fixture will give test functions a ready instantiated plugin
# (and having the `client` fixture, a clean setup every unit)
@pytest.fixture(scope="function")
def plugin(lizard):
    p = Plugin(mock_plugin_path)
    yield p


@pytest.fixture(scope="function")
def mocked_default_llm_answer_prompt():
    def mock_default_llm_answer_prompt() -> str:
        return "Ops AI: You did not configure a Language Model. Do it in the settings!"

    fnc = utils.default_llm_answer_prompt
    utils.default_llm_answer_prompt = mock_default_llm_answer_prompt

    yield

    utils.default_llm_answer_prompt = fnc


# Define the custom marker
pytest.mark.skip_encapsulation = pytest.mark.skip_encapsulation
