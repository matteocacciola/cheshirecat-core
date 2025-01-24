import asyncio
import pytest
import pytest_asyncio
import os
import shutil
import redis
from typing import Any, Generator
import warnings
from pydantic import PydanticDeprecatedSince20
from qdrant_client import AsyncQdrantClient
from fastapi.testclient import TestClient
import time

from cat.auth import auth_utils
from cat.auth.permissions import AuthUserInfo, get_base_permissions
from cat.convo.messages import UserMessage
from cat.db.database import Database
from cat.db.vector_database import VectorDatabase, LOCAL_FOLDER_PATH
from cat.env import get_env
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.looking_glass.stray_cat import StrayCat
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.plugin import Plugin
from cat.memory.vector_memory_builder import VectorMemoryBuilder
from cat.startup import cheshire_cat_api
import cat.utils as utils


from tests.utils import (
    agent_id,
    api_key,
    api_key_ws,
    jwt_secret,
    create_mock_plugin_zip,
    get_class_from_decorated_singleton,
    mock_plugin_path,
    fake_timestamp,
)

pytest_plugins = ['pytest_asyncio']
redis_client = redis.Redis(host=get_env("CCAT_REDIS_HOST"), db="1", encoding="utf-8", decode_responses=True)


# substitute classes' methods where necessary for testing purposes
def mock_classes(monkeypatch):
    # Use in memory vector db
    def mock_connect_to_vector_memory(self, *args, **kwargs):
        return AsyncQdrantClient(":memory:")
    monkeypatch.setattr(
        get_class_from_decorated_singleton(VectorDatabase), "connect_to_vector_memory", mock_connect_to_vector_memory
    )

    # Use a different redis client
    def mock_get_redis_client(self, *args, **kwargs):
        return redis_client
    monkeypatch.setattr(get_class_from_decorated_singleton(Database), "get_redis_client", mock_get_redis_client)

    utils.get_plugins_path = lambda: "tests/mocks/mock_plugin_folder/"
    utils.get_file_manager_root_storage_path = lambda: "tests/data/storage"

    # do not check plugin dependencies at every restart
    def mock_install_requirements(self, *args, **kwargs):
        pass
    monkeypatch.setattr(Plugin, "_install_requirements", mock_install_requirements)

    # mock the agent_id in the request
    auth_utils.extract_agent_id_from_request = lambda: agent_id


def clean_up():
    # clean up service files and mocks
    to_be_removed = [
        "tests/mocks/mock_plugin.zip",
        "tests/mocks/mock_plugin_fast_reply.zip",
        "tests/mocks/mock_plugin/settings.json",
        "tests/mocks/mock_plugin_folder/mock_plugin",
        "tests/mocks/mock_plugin_folder/mock_plugin_fast_reply",
        "tests/mocks/mock_plugin/settings.py",
        "tests/mocks/empty_folder",
        "tests/data",
    ]
    for tbr in to_be_removed:
        if os.path.exists(tbr):
            if os.path.isdir(tbr):
                shutil.rmtree(tbr)
            else:
                os.remove(tbr)

    redis_client.flushdb()

    # wait for the flushdb to be completed
    time.sleep(0.1)


# remove the local Qdrant memory
def clean_up_qdrant():
    # remove the local Qdrant memory
    if os.path.exists(LOCAL_FOLDER_PATH):
        shutil.rmtree(LOCAL_FOLDER_PATH)


def should_skip_encapsulation(request):
    return request.node.get_closest_marker("skip_encapsulation") is not None


@pytest_asyncio.fixture(autouse=True)
async def encapsulate_each_test(request, monkeypatch):
    if should_skip_encapsulation(request):
        # Skip initialization for tests marked with @pytest.mark.skip_initialization
        yield

        return

    clean_up_qdrant()

    # monkeypatch classes
    mock_classes(monkeypatch)

    # env variables
    current_debug = get_env("CCAT_DEBUG")
    os.environ["CCAT_DEBUG"] = "false"  # do not autoreload
    current_rabbit_hole_storage_enabled = get_env("CCAT_RABBIT_HOLE_STORAGE_ENABLED")
    os.environ["CCAT_RABBIT_HOLE_STORAGE_ENABLED"] = "true"

    # clean up tmp files, folders and redis database
    clean_up()

    # delete all singletons!!!
    utils.singleton.instances = {}

    memory_builder = VectorMemoryBuilder()
    await memory_builder.build()

    yield

    # clean up tmp files, folders and redis database
    clean_up()

    if current_debug:
        os.environ["CCAT_DEBUG"] = current_debug
    else:
        del os.environ["CCAT_DEBUG"]
    if current_rabbit_hole_storage_enabled:
        os.environ["CCAT_RABBIT_HOLE_STORAGE_ENABLED"] = current_rabbit_hole_storage_enabled
    else:
        del os.environ["CCAT_RABBIT_HOLE_STORAGE_ENABLED"]

    clean_up_qdrant()


@pytest.fixture(scope="function")
def lizard():
    l = BillTheLizard().set_fastapi_app(cheshire_cat_api)
    yield l
    l.shutdown()


@pytest.fixture(scope="function")
def white_rabbit():
    wr = WhiteRabbit()
    yield wr
    wr.shutdown()


@pytest_asyncio.fixture(scope="function")
async def cheshire_cat(lizard):
    cheshire_cat = await lizard.create_cheshire_cat(agent_id)

    yield cheshire_cat


# Main fixture for the FastAPI app
@pytest_asyncio.fixture(scope="function")
async def client(cheshire_cat) -> Generator[TestClient, Any, None]:
    """
    Create a new FastAPI TestClient.
    """

    with TestClient(cheshire_cat_api) as client:
        yield client


# This fixture sets the CCAT_API_KEY and CCAT_API_KEY_WS environment variables,
# making mandatory for clients to possess api keys or JWT
@pytest_asyncio.fixture(scope="function")
async def secure_client(client):
    current_api_key = os.getenv("CCAT_API_KEY")
    current_api_ws = os.getenv("CCAT_API_KEY_WS")
    current_jwt_secret = os.getenv("CCAT_JWT_SECRET")

    # set ENV variables
    os.environ["CCAT_API_KEY"] = api_key
    os.environ["CCAT_API_KEY_WS"] = api_key_ws
    os.environ["CCAT_JWT_SECRET"] = jwt_secret

    yield client

    # clean up
    if current_api_key:
        os.environ["CCAT_API_KEY"] = current_api_key
    else:
        del os.environ["CCAT_API_KEY"]
    if current_api_ws:
        os.environ["CCAT_API_KEY_WS"] = current_api_ws
    else:
        del os.environ["CCAT_API_KEY_WS"]
    if current_jwt_secret:
        os.environ["CCAT_JWT_SECRET"] = current_jwt_secret
    else:
        del os.environ["CCAT_JWT_SECRET"]


@pytest.fixture(scope="function")
def secure_client_headers():
    yield {"agent_id": agent_id, "Authorization": f"Bearer {api_key}"}


@pytest.fixture(scope="function")
def plugin_manager(lizard):
    plugin_manager = lizard.plugin_manager

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    plugin_manager.install_plugin(new_plugin_zip_path)

    yield plugin_manager

    plugin_manager.uninstall_plugin("mock_plugin")


@pytest.fixture(scope="function")
def agent_plugin_manager(cheshire_cat):
    plugin_manager = cheshire_cat.plugin_manager

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    plugin_id = cheshire_cat.lizard.plugin_manager.install_plugin(new_plugin_zip_path)

    # activate the plugin within the Cheshire Cat whose plugin manager is being used
    plugin_manager.toggle_plugin(plugin_id)

    yield plugin_manager


@pytest.fixture(scope="function")
def embedder(lizard):
    yield lizard.embedder


@pytest.fixture(scope="function")
def llm(cheshire_cat):
    yield cheshire_cat.large_language_model


@pytest_asyncio.fixture(scope="function")
async def memory(cheshire_cat):
    yield cheshire_cat.memory


@pytest_asyncio.fixture(scope="function")
async def stray_no_memory(cheshire_cat, lizard) -> StrayCat:
    stray_cat = StrayCat(
        user_data=AuthUserInfo(id="user_alice", name="Alice", permissions=get_base_permissions()),
        agent_id=cheshire_cat.id
    )

    # install plugin
    new_plugin_zip_path = create_mock_plugin_zip(flat=True)
    plugin_id = lizard.plugin_manager.install_plugin(new_plugin_zip_path)

    # activate the plugin within the Cheshire Cat whose plugin manager is being used
    cheshire_cat.plugin_manager.toggle_plugin(plugin_id)

    yield stray_cat


# fixture to have available an instance of StrayCat
@pytest_asyncio.fixture(scope="function")
async def stray(stray_no_memory):
    stray_no_memory.working_memory.user_message = UserMessage(text="meow")
    yield stray_no_memory


# autouse fixture will be applied to *all* the tests
@pytest.fixture(autouse=True)
def apply_warning_filters():
    # ignore deprecation warnings due to langchain not updating to pydantic v2
    warnings.filterwarnings("ignore", category=PydanticDeprecatedSince20)


#fixture for mock time.time function
@pytest.fixture(scope="function")
def patch_time_now(monkeypatch):
    def mytime():
        return fake_timestamp

    monkeypatch.setattr(time, 'time', mytime)


# this fixture will give test functions a ready instantiated plugin
# (and having the `client` fixture, a clean setup every unit)
@pytest.fixture(scope="function")
def plugin():
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
