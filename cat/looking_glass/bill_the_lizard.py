from copy import deepcopy
from typing import Dict, List
from uuid import uuid4
from fastapi import FastAPI
from langchain_core.embeddings import Embeddings

from cat.auth.auth_utils import hash_password, DEFAULT_ADMIN_USERNAME
from cat.auth.permissions import get_full_admin_permissions
from cat.db import crud
from cat.db.cruds import settings as crud_settings, users as crud_users
from cat.db.database import DEFAULT_SYSTEM_KEY, UNALLOWED_AGENT_KEYS
from cat.env import get_env
from cat.exceptions import LoadMemoryException
from cat.factory.auth_handler import CoreAuthHandler
from cat.factory.embedder import EmbedderFactory
from cat.log import log
from cat.looking_glass.humpty_dumpty import HumptyDumpty, subscriber
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.tweedledum import Tweedledum
from cat.mad_hatter.decorators import CustomEndpoint
from cat.rabbit_hole import RabbitHole
from cat.services.websocket_manager import WebSocketManager
from cat.utils import (
    singleton,
    explicit_error_message,
    get_factory_object,
    get_nlp_object_name,
    get_updated_factory_object,
)


@singleton
class BillTheLizard:
    """
    Singleton class that manages the Cheshire Cats and their strays.

    The Cheshire Cats are the agents that are currently active and have users to attend.
    The strays are the users that are waiting for an agent to attend them.

    The Bill The Lizard Manager is responsible for:
    - Creating and deleting Cheshire Cats
    - Adding and removing strays from Cheshire Cats
    - Getting the Cheshire Cat of a stray
    - Getting the strays of a Cheshire Cat
    """
    def __init__(self):
        """
        Bill the Lizard initialization.
        At init time the Lizard executes the bootstrap.

        Notes
        -----
        Bootstrapping is the process of loading the plugins, the Embedder, the *Main Agent*, the *Rabbit Hole* and
        the *White Rabbit*.
        """
        self.dispatcher = HumptyDumpty()
        self.dispatcher.subscribe_from(self)

        self._key = DEFAULT_SYSTEM_KEY

        self._fastapi_app = None
        self._pending_endpoints = []

        self.embedder: Embeddings | None = None
        self.embedder_size: int | None = None

        # load active plugins
        self.plugin_manager = Tweedledum()
        self.plugin_manager.discover_plugins()

        # allows plugins to do something before cat components are loaded
        self.plugin_manager.execute_hook("before_lizard_bootstrap", obj=self)

        self.websocket_manager = WebSocketManager()

        # load embedder
        self.load_language_embedder()

        # Rabbit Hole Instance
        self.rabbit_hole = RabbitHole()

        self.core_auth_handler = CoreAuthHandler()

        # Initialize the default admin if not present
        if not crud_users.get_users(self._key):
            self.initialize_users()

        self.plugin_manager.execute_hook("after_lizard_bootstrap", obj=self)

    @subscriber("on_end_plugin_install")
    def on_end_plugin_install(self, plugin_id: str, plugin_path: str) -> None:
        # Store endpoints for later activation
        self._pending_endpoints = deepcopy(self.plugin_manager.plugins[plugin_id].endpoints)

        # If app is already available, activate immediately
        if self.fastapi_app is not None:
            self._activate_pending_endpoints()

        self.plugin_manager.execute_hook("lizard_notify_plugin_installation", plugin_id, plugin_path, obj=self)

    @subscriber("on_start_plugin_uninstall")
    def on_start_plugin_uninstall(self, plugin_id: str) -> None:
        # deactivate plugins in the Cheshire Cats
        self.on_start_plugin_deactivate(plugin_id)

    @subscriber("on_end_plugin_uninstall")
    def on_end_plugin_uninstall(self, plugin_id: str, endpoints: List[CustomEndpoint]) -> None:
        # Store endpoints for later activation
        self._pending_endpoints = endpoints

        # If app is already available, activate immediately
        if self.fastapi_app is not None:
            self._deactivate_pending_endpoints(plugin_id)

        self.plugin_manager.execute_hook("lizard_notify_plugin_uninstallation", plugin_id, obj=self)

    @subscriber("on_finish_plugins_sync")
    def on_finish_plugins_sync(self, with_endpoints: bool) -> None:
        if not with_endpoints:
            return

        # Store endpoints for later activation
        self._pending_endpoints = deepcopy(self.plugin_manager.endpoints)

        # If app is already available, activate immediately
        if self.fastapi_app is not None:
            self._activate_pending_endpoints()

    @subscriber("on_end_plugin_activate")
    def on_end_plugin_activate(self, plugin_id: str) -> None:
        # migrate plugin settings in the Cheshire Cats
        for ccat_id in crud.get_agents_plugin_keys(plugin_id):
            ccat = self.get_cheshire_cat(ccat_id)
            # if the plugin is not active for the Cheshire Cat, then skip it
            if not ccat.plugin_manager.local_plugin_exists(plugin_id):
                continue
            # if the plugin is active for the Cheshire Cat, then re-activate to incrementally apply the new settings
            ccat.plugin_manager.activate_plugin(plugin_id, dispatch_events=False)

    @subscriber("on_start_plugin_deactivate")
    def on_start_plugin_deactivate(self, plugin_id: str) -> None:
        # deactivate plugins in the Cheshire Cats
        for ccat_id in crud.get_agents_plugin_keys(plugin_id):
            ccat = self.get_cheshire_cat(ccat_id)
            ccat.plugin_manager.deactivate_plugin(plugin_id, dispatch_events=False)

    def _activate_pending_endpoints(self) -> None:
        for endpoint in self._pending_endpoints:
            endpoint.activate(self.fastapi_app)
        self._pending_endpoints.clear()

    def _deactivate_pending_endpoints(self, plugin_id: str) -> None:
        for endpoint in self._pending_endpoints:
            if endpoint.plugin_id == plugin_id:
                endpoint.deactivate(self.fastapi_app)
        self._pending_endpoints.clear()

    def initialize_users(self):
        admin_id = str(uuid4())

        crud_users.set_users(self._key, {
            admin_id: {
                "id": admin_id,
                "username": DEFAULT_ADMIN_USERNAME,
                "password": hash_password(get_env("CCAT_ADMIN_DEFAULT_PASSWORD")),
                # admin has all permissions
                "permissions": get_full_admin_permissions()
            }
        })

    def load_language_embedder(self):
        """
        Hook into the embedder selection. Allows to modify how the Lizard selects the embedder at bootstrap time.
        """
        factory = EmbedderFactory(self.plugin_manager)

        # Get embedder size (langchain classes do not store it)
        self.embedder = get_factory_object(self._key, factory)
        self.embedder_size = len(self.embedder.embed_query("hello world"))

    async def replace_embedder(self, language_embedder_name: str, settings: Dict) -> Dict:
        """
        Replace the current embedder with a new one. This method is used to change the embedder of the lizard.

        Args:
            language_embedder_name: name of the new embedder
            settings: settings of the new embedder

        Returns:
            The dictionary resuming the new name and settings of the embedder
        """
        factory = EmbedderFactory(self.plugin_manager)
        updater = get_updated_factory_object(self._key, factory, language_embedder_name, settings)

        try:
            # reload the embedder of the lizard
            self.load_language_embedder()

            for ccat_id in crud.get_agents_main_keys():
                ccat = self.get_cheshire_cat(ccat_id)

                # inform the Cheshire Cats about the new embedder available in the system
                await ccat.vector_memory_handler.initialize(self.embedder_name, self.embedder_size)
        except Exception as e:  # restore the original Embedder
            log.error(e)

            # something went wrong: rollback
            if updater.old_setting is not None:
                await self.replace_embedder(updater.old_setting["name"], updater.old_setting["value"])

            raise LoadMemoryException(f"Load memory exception: {explicit_error_message(e)}")

        return {"name": language_embedder_name, "value": updater.new_setting["value"]}

    def get_cheshire_cat(self, agent_id: str) -> CheshireCat | None:
        """
        Get the Cheshire Cat with the given id, directly from db.

        Args:
            agent_id: The id of the agent to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """
        if agent_id == DEFAULT_SYSTEM_KEY:
            raise ValueError(f"`{DEFAULT_SYSTEM_KEY}` is a reserved name for agents")

        if agent_id not in crud.get_agents_main_keys():
            raise ValueError(f"`{agent_id}` is not a valid agent id")

        return CheshireCat(agent_id)

    async def create_cheshire_cat(self, agent_id: str) -> CheshireCat:
        """
        Create the Cheshire Cat with the given id, directly from db.

        Args:
            agent_id: The id of the agent to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """
        if agent_id in UNALLOWED_AGENT_KEYS:
            raise ValueError(f"{agent_id} is not allowed as name for agents")

        if agent_id in crud.get_agents_main_keys():
            return self.get_cheshire_cat(agent_id)

        ccat = CheshireCat(agent_id)
        await ccat.embed_procedures()

        return ccat

    def get_cheshire_cat_from_db(self, agent_id: str) -> CheshireCat | None:
        """
        Gets the Cheshire Cat with the given id, directly from db.

        Args:
            agent_id: The id of the agent to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """
        agent_settings = crud_settings.get_settings(agent_id)
        if not agent_settings:
            return None

        return self.get_cheshire_cat(agent_id)

    async def shutdown(self) -> None:
        """
        Shuts down the Bill The Lizard Manager. It closes all the strays' connections and stops the scheduling system.

        Returns:
            None
        """
        self.plugin_manager.execute_hook("before_lizard_shutdown", obj=self)

        self.dispatcher.unsubscribe_from(self)

        if self.websocket_manager:
            await self.websocket_manager.close_all_connections()

        self.core_auth_handler = None
        self.plugin_manager = None
        self.rabbit_hole = None
        self.embedder = None
        self.embedder_size = None
        self.websocket_manager = None
        self.fastapi_app = None

    @property
    def fastapi_app(self):
        return self._fastapi_app

    @fastapi_app.setter
    def fastapi_app(self, app: FastAPI | None = None):
        self._fastapi_app = app
        # Activate any pending endpoints
        if app is not None:
            self._activate_pending_endpoints()

    @property
    def config_key(self):
        return self._key

    @property
    def agent_key(self):
        return self._key

    @property
    def embedder_name(self) -> str | None:
        if self.embedder is None:
            return None
        return get_nlp_object_name(self.embedder, "default_embedder")
