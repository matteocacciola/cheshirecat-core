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
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.looking_glass.mad_hatter.registry import PluginRegistry
from cat.rabbit_hole import RabbitHole
from cat.services.factory.auth_handler import CoreAuthHandler
from cat.services.memory.models import VectorMemoryType, PointStruct
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
        self._plugin_registry = None

        self._fastapi_app = None

        # load active plugins
        self.plugin_manager = MadHatter(self.agent_key)
        self.plugin_manager.discover_plugins()

        # Store endpoints for later activation
        self._pending_endpoints = deepcopy(self.plugin_manager.endpoints)

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
        if agent_id == DEFAULT_SYSTEM_KEY:
            raise ValueError(f"{agent_id} is not allowed as name for agents")

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
                points=[PointStruct(**p.model_dump()) for p in points],
            )
        await cloned_ccat.embed_procedures()

        # clone the files from the ccat to the provided agent
        log.info(f"Cloning files from agent {ccat.agent_key} to agent {new_agent_id}")
        ccat.file_manager.clone_folder(ccat.agent_key, new_agent_id)

        return cloned_ccat

    async def embed_all_in_cheshire_cats(self, embedder_name: str, embedder_size: int) -> None:
        """Re-embeds all the stored files and procedures in all the Cheshire Cats using the current embedder."""
        async def embed_with_limit(entry_):
            async with semaphore:
                await entry_["ccat"].embed_all(entry_["stored_sources"])

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
        # limit concurrent embeddings to avoid overwhelming resources
        semaphore = asyncio.Semaphore(5)  # Max 5 concurrent
        await asyncio.gather(*[
            embed_with_limit(entry)
            for entry in stored_files_by_ccat
        ])

    def is_custom_endpoint(self, path: str, methods: List[str] | None = None):
        """
        Check if the given path and methods correspond to a custom endpoint.

        Args:
            path (str): The path of the endpoint to check.
            methods (List[str] | None): The HTTP methods of the endpoint to check. If None, checks all methods.

        Returns:
            bool: True if the endpoint is a custom endpoint, False otherwise.
        """
        return any(
            ep.real_path == path and (methods is None or set(ep.methods) == set(methods))
            for ep in self.plugin_manager.endpoints
        )

    def install_plugin(self, plugin_path: str) -> str:
        plugin_id = ""
        try:
            plugin_id = self.plugin_manager.install_plugin(plugin_path)

            self.on_plugin_activate(plugin_id)
            self.plugin_manager.execute_hook(
                "lizard_notify_plugin_installation", plugin_id, plugin_path, caller=self,
            )

            return plugin_id
        except Exception as e:
            log.error(f"Could not install plugin from {plugin_path}: {e}")
            raise e
        finally:
            self.plugin_manager.execute_hook(
                "lizard_notify_plugin_installation", plugin_id, plugin_path, caller=self,
            )

    def uninstall_plugin(self, plugin_id: str, dispatch_event: bool = True):
        try:
            # deactivate plugins in the Cheshire Cats
            if plugin_id in self.plugin_manager.active_plugins:
                self.on_plugin_deactivate(plugin_id)

            self.plugin_manager.uninstall_plugin(plugin_id)
        except Exception as e:
            log.error(f"Could not uninstall plugin {plugin_id}: {e}")
            raise e
        finally:
            if dispatch_event:
                self.plugin_manager.execute_hook(
                    "lizard_notify_plugin_uninstallation", plugin_id, caller=self,
                )

    def toggle_plugin(self, plugin_id: str):
        # the plugin is active, and evidently I am deactivating it: deactivate it in the Cheshire Cats before
        # deactivating it on a system level
        if plugin_id in self.plugin_manager.active_plugins:
            self.on_plugin_deactivate(plugin_id)

        # toggle (activate or deactivate) the plugin
        self.plugin_manager.toggle_plugin(plugin_id)

        if plugin_id in self.plugin_manager.active_plugins:
            self.on_plugin_activate(plugin_id)

    def on_plugin_activate(self, plugin_id: str) -> None:
        # Store endpoints for later activation
        self._pending_endpoints = deepcopy(self.plugin_manager.plugins[plugin_id].endpoints)
        self._activate_pending_endpoints()

        # if I already installed and activated the plugin and I am now re-installing it, then migrate plugin settings in
        # the Cheshire Cats to incrementally apply the new settings
        for ccat_id in crud_plugins.get_agents_plugin_keys(plugin_id):
            # if the plugin is not active for the Cheshire Cat, then skip it
            if (ccat := self._get_cheshire_cat_on_plugin_event(ccat_id, plugin_id)) is None:
                continue
            ccat.plugin_manager.activate_plugin(plugin_id)

    def on_plugin_deactivate(self, plugin_id: str):
        # deactivate the endpoints from the plugin
        if endpoints := self.plugin_manager.plugins[plugin_id].endpoints:
            for endpoint in endpoints:
                endpoint.deactivate(self.fastapi_app)

        for ccat_id in crud_plugins.get_agents_plugin_keys(plugin_id):
            # if the plugin is not active for the Cheshire Cat, then skip it
            if (ccat := self._get_cheshire_cat_on_plugin_event(ccat_id, plugin_id)) is None:
                continue
            ccat.plugin_manager.deactivate_plugin(plugin_id)

    def _activate_pending_endpoints(self) -> None:
        for endpoint in self._pending_endpoints:
            endpoint.activate(self.fastapi_app)
        self._pending_endpoints.clear()

    async def shutdown(self) -> None:
        """
        Shuts down the Bill The Lizard Manager. It closes all the strays' connections and stops the scheduling system.

        Returns:
            None
        """
        self.plugin_manager.execute_hook("before_lizard_shutdown", caller=self)
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
