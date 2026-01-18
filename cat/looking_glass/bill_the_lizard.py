import asyncio
from copy import deepcopy
from typing import List, Dict
from fastapi import FastAPI

from cat.auth.auth_utils import hash_password, DEFAULT_ADMIN_USERNAME
from cat.auth.permissions import get_full_permissions
from cat.db import crud
from cat.db.cruds import settings as crud_settings, users as crud_users, plugins as crud_plugins
from cat.db.database import DEFAULT_SYSTEM_KEY, DEFAULT_CONVERSATIONS_KEY
from cat.env import get_env
from cat.log import log
from cat.looking_glass.humpty_dumpty import HumptyDumpty, subscriber
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.mad_hatter.decorators.endpoint import CatEndpoint
from cat.looking_glass.mad_hatter.registry import PluginRegistry
from cat.looking_glass.tweedledum import Tweedledum
from cat.rabbit_hole import RabbitHole
from cat.services.factory.auth_handler import CoreAuthHandler
from cat.services.memory.models import VectorMemoryType
from cat.services.mixin import OrchestratorMixin
from cat.services.websocket_manager import WebSocketManager
from cat.utils import singleton, sanitize_permissions


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

        self._plugin_registry = None

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
        for ccat_id in crud_plugins.get_agents_plugin_keys(plugin_id):
            # if the plugin is not active for the Cheshire Cat, then skip it
            if (ccat := self._get_cheshire_cat_on_plugin_event(ccat_id, plugin_id)) is None:
                continue
            # if the plugin is active for the Cheshire Cat, then re-activate to incrementally apply the new settings
            ccat.plugin_manager.activate_plugin(plugin_id, dispatch_events=False)

    @subscriber("on_start_plugin_deactivate")
    def on_start_plugin_deactivate(self, plugin_id: str) -> None:
        # deactivate plugins in the Cheshire Cats
        for ccat_id in crud_plugins.get_agents_plugin_keys(plugin_id):
            # if the plugin is not active for the Cheshire Cat, then skip it
            if (ccat := self._get_cheshire_cat_on_plugin_event(ccat_id, plugin_id)) is None:
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

        permissions = sanitize_permissions(get_full_permissions(), self.agent_key)

        crud_users.create_user(self.agent_key, {
            "username": DEFAULT_ADMIN_USERNAME,
            "password": hash_password(get_env("CCAT_ADMIN_DEFAULT_PASSWORD")),
            "permissions": permissions,  # base admin has all permissions, but CHAT
        })

    async def create_cheshire_cat(self, agent_id: str) -> CheshireCat:
        """
        Create the Cheshire Cat with the given id, directly from db.

        Args:
            agent_id: The id of the agent to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """
        if agent_id in crud.get_agents_main_keys():
            return self.get_cheshire_cat(agent_id)

        ccat = None
        try:
            ccat = CheshireCat(agent_id)
            ccat.bootstrap_services()
            await ccat.vector_memory_handler.initialize(self.embedder_name, self.embedder_size)
            await ccat.embed_procedures()

            return ccat
        except Exception as e:
            log.error(f"Error creating Cheshire Cat `{agent_id}`: {e}")
            await self.rollback_cheshire_cat_creation(agent_id, ccat)

            raise

    async def rollback_cheshire_cat_creation(self, agent_id: str, cat: CheshireCat | None) -> None:
        """
        Rollback the creation of a Cheshire Cat with the given id.

        Args:
            agent_id: The id of the agent to rollback
            cat: The Cheshire Cat to rollback

        Returns:
            None
        """
        # rollback
        if cat:
            await cat.destroy()
            return

        crud.delete(agent_id)

    def _get_cheshire_cat_on_plugin_event(self, agent_id: str, plugin_id: str) -> CheshireCat | None:
        """
        Determines and retrieves the CheshireCat object associated with a specific plugin event for a given agent if the
        plugin is active.

        Args:
            agent_id (str): The unique identifier for the agent.
            plugin_id (str): The unique identifier for the plugin.

        Returns:
            CheshireCat | None: The CheshireCat object if the plugin is active, otherwise None.
        """
        active_plugins = crud_plugins.get_active_plugins_from_db(agent_id)
        if not active_plugins or plugin_id not in active_plugins:
            return None

        return self.get_cheshire_cat(agent_id)

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

    async def clone_cheshire_cat(self, ccat: CheshireCat, new_agent_id: str) -> CheshireCat:
        """
        Clone a Cheshire Cat into a new one.

        Args:
            ccat: The Cheshire Cat to clone.
            new_agent_id: The new agent id to clone into.

        Returns:
            The cloned Cheshire Cat.
        """
        # clone the settings from the provided agent
        log.info(f"Cloning settings from agent {ccat.agent_key} to agent {new_agent_id}")
        crud.clone_agent(ccat.agent_key, new_agent_id, [DEFAULT_CONVERSATIONS_KEY])

        # clone the vector points from the ccat to the provided agent
        cloned_ccat = self.get_cheshire_cat(new_agent_id)
        await cloned_ccat.vector_memory_handler.initialize(self.embedder_name, self.embedder_size)

        log.info(f"Cloning vector memory from agent {ccat.agent_key} to agent {new_agent_id}")
        collection_name = str(VectorMemoryType.DECLARATIVE)
        points, _ = await ccat.vector_memory_handler.get_all_tenant_points(collection_name, with_vectors=True)
        if points:
            await cloned_ccat.vector_memory_handler.add_points_to_tenant(
                collection_name=collection_name,
                payloads=[p.payload for p in points],
                vectors=[p.vector for p in points],
            )
        await cloned_ccat.embed_procedures()

        # clone the files from the ccat to the provided agent
        log.info(f"Cloning files from agent {ccat.agent_key} to agent {new_agent_id}")
        ccat.file_manager.clone_folder(ccat.agent_key, new_agent_id)

        return cloned_ccat

    async def embed_all_in_cheshire_cats(self, embedder_name: str, embedder_size: int) -> None:
        """Re-embeds all the stored files and procedures in all the Cheshire Cats using the current embedder."""
        ccat_ids = crud.get_agents_main_keys()
        stored_files_by_ccat: List[Dict] = []
        # first, I need to get all the stored files from all the Cheshire Cats with the metadata stored
        # within the vector memory; I do not remove anything from the latter to avoid any race condition
        for ccat_id in ccat_ids:
            if (ccat := self.get_cheshire_cat(ccat_id)) is None:
                continue

            stored_files_by_ccat.append({
                "ccat": ccat,
                "stored_sources": await ccat.get_stored_sources_with_metadata(),
            })

        # now, I have to re-initialize all the vector databases in a serialized way, outside threads to avoid
        # race conditions
        for entry in stored_files_by_ccat:
            await entry["ccat"].vector_memory_handler.initialize(embedder_name, embedder_size)

        # finally, I can re-embed all the stored files in an asynchronous way
        for entry in stored_files_by_ccat:
            asyncio.create_task(entry["ccat"].embed_all(entry["stored_sources"]))

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
    def plugin_registry(self) -> PluginRegistry:
        return self._plugin_registry

    @plugin_registry.setter
    def plugin_registry(self, registry: PluginRegistry):
        self._plugin_registry = registry

    @property
    def config_key(self):
        return self.agent_key

    @property
    def agent_key(self):
        return DEFAULT_SYSTEM_KEY
