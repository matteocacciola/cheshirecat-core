from copy import deepcopy
from typing import List
from fastapi import FastAPI

from cat.auth.auth_utils import hash_password, DEFAULT_ADMIN_USERNAME
from cat.auth.permissions import get_full_permissions
from cat.db import crud
from cat.db.cruds import settings as crud_settings, users as crud_users
from cat.db.database import DEFAULT_SYSTEM_KEY, UNALLOWED_AGENT_KEYS
from cat.env import get_env
from cat.log import log
from cat.looking_glass.humpty_dumpty import HumptyDumpty, subscriber
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.mad_hatter.decorators.endpoint import CatEndpoint
from cat.looking_glass.tweedledum import Tweedledum
from cat.rabbit_hole import RabbitHole
from cat.services.factory.auth_handler import CoreAuthHandler
from cat.services.mixin import OrchestratorMixin
from cat.services.websocket_manager import WebSocketManager
from cat.utils import singleton


@singleton
class BillTheLizard(OrchestratorMixin):
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

        self._fastapi_app = None
        self._pending_endpoints = []

        # load active plugins
        self.plugin_manager = Tweedledum()
        self.plugin_manager.discover_plugins()

        # allows plugins to do something before cat components are loaded
        self.plugin_manager.execute_hook("before_lizard_bootstrap", caller=self)

        # bootstrap bill the lizard
        super().__init__()

        self.websocket_manager = WebSocketManager()

        # Rabbit Hole Instance
        self.rabbit_hole = RabbitHole()

        self.core_auth_handler = CoreAuthHandler()

        # Initialize the default admin if not present
        if not crud_users.get_users(self.agent_key):
            self.initialize_users()

        self.plugin_manager.execute_hook("after_lizard_bootstrap", caller=self)

    def bootstrap_services(self):
        self.service_provider.bootstrap_services_orchestrator()

    @subscriber("on_end_plugin_install")
    def on_end_plugin_install(self, plugin_id: str, plugin_path: str) -> None:
        # Store endpoints for later activation
        self._pending_endpoints = deepcopy(self.plugin_manager.plugins[plugin_id].endpoints)

        # If app is already available, activate immediately
        if self.fastapi_app is not None:
            self._activate_pending_endpoints()

        self.plugin_manager.execute_hook("lizard_notify_plugin_installation", plugin_id, plugin_path, caller=self)

    @subscriber("on_start_plugin_uninstall")
    def on_start_plugin_uninstall(self, plugin_id: str) -> None:
        # deactivate plugins in the Cheshire Cats
        self.on_start_plugin_deactivate(plugin_id)

    @subscriber("on_end_plugin_uninstall")
    def on_end_plugin_uninstall(self, plugin_id: str, endpoints: List[CatEndpoint]) -> None:
        # Store endpoints for later activation
        self._pending_endpoints = endpoints

        # If app is already available, activate immediately
        if self.fastapi_app is not None:
            self._deactivate_pending_endpoints(plugin_id)

        self.plugin_manager.execute_hook("lizard_notify_plugin_uninstallation", plugin_id, caller=self)

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
            if ccat is None or not ccat.plugin_manager.local_plugin_exists(plugin_id):
                continue
            # if the plugin is active for the Cheshire Cat, then re-activate to incrementally apply the new settings
            ccat.plugin_manager.activate_plugin(plugin_id, dispatch_events=False)

    @subscriber("on_start_plugin_deactivate")
    def on_start_plugin_deactivate(self, plugin_id: str) -> None:
        # deactivate plugins in the Cheshire Cats
        for ccat_id in crud.get_agents_plugin_keys(plugin_id):
            ccat = self.get_cheshire_cat(ccat_id)
            if ccat is None:
                continue
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
        crud_users.initialize_empty_users(self.agent_key)
        crud_users.create_user(self.agent_key, {
            "username": DEFAULT_ADMIN_USERNAME,
            "password": hash_password(get_env("CCAT_ADMIN_DEFAULT_PASSWORD")),
            # base admin has all permissions
            "permissions": get_full_permissions(),
        })

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
        ccat.bootstrap_services()
        await ccat.embed_procedures()

        return ccat

    def get_cheshire_cat(self, agent_id: str) -> CheshireCat | None:
        """
        Gets the Cheshire Cat with the given id, directly from db.

        Args:
            agent_id: The id of the agent to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """
        if agent_id == DEFAULT_SYSTEM_KEY:
            log.debug("The system agent has been requested: returning null value.")
            return None

        if agent_id not in crud.get_agents_main_keys():
            log.debug(f"Requested not existing `{agent_id}`")
            raise ValueError("Bad Request")

        agent_settings = crud_settings.get_settings(agent_id)
        if not agent_settings:
            log.debug(f"Agent `{agent_id}` has no settings")
            return None

        return CheshireCat(agent_id)

    async def shutdown(self) -> None:
        """
        Shuts down the Bill The Lizard Manager. It closes all the strays' connections and stops the scheduling system.

        Returns:
            None
        """
        self.plugin_manager.execute_hook("before_lizard_shutdown", caller=self)

        self.dispatcher.unsubscribe_from(self)

        if self.websocket_manager:
            await self.websocket_manager.close_all_connections()

        self.core_auth_handler = None
        self.plugin_manager = None
        self.rabbit_hole = None
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
        return self.agent_key

    @property
    def agent_key(self):
        return DEFAULT_SYSTEM_KEY
