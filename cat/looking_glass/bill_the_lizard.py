import json
import threading
from copy import deepcopy
from typing import Dict, Literal, List
from uuid import uuid4
from fastapi import FastAPI
from langchain_core.embeddings import Embeddings

from cat import utils
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
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.mad_hatter import MadHatter, MarchHare, MarchHareConfig, Tweedledum
from cat.mad_hatter.decorators import CustomEndpoint
from cat.rabbit_hole import RabbitHole
from cat.services.websocket_manager import WebSocketManager
from cat.utils import (
    singleton,
    get_embedder_name,
    dispatch,
    get_factory_object,
    get_updated_factory_object,
    pod_id,
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
        self._key = DEFAULT_SYSTEM_KEY
        self._pod_id = pod_id()

        self._fastapi_app = None
        self._pending_endpoints = []

        self.embedder: Embeddings | None = None
        self.embedder_name: str | None = None
        self.embedder_size: int | None = None

        self.plugin_manager = Tweedledum()
        self.plugin_manager.on_end_plugin_install_callback = self._on_end_plugin_install
        self.plugin_manager.on_start_plugin_uninstall_callback = self._on_start_plugin_uninstall
        self.plugin_manager.on_end_plugin_uninstall_callback = self._on_end_plugin_uninstall
        self.plugin_manager.on_finish_plugins_sync_callback = self._on_finish_plugins_sync
        self.plugin_manager.on_end_plugin_toggle_callback = self._on_end_plugin_toggle
        # load active plugins
        self.plugin_manager.find_plugins()

        self.websocket_manager = WebSocketManager()

        # load embedder
        self.load_language_embedder()

        # Rabbit Hole Instance
        self.rabbit_hole = RabbitHole()

        self.core_auth_handler = CoreAuthHandler()

        # March Hare instance (for RabbitMQ management)
        self.march_hare = MarchHare()

        # Initialize the default admin if not present
        if not crud_users.get_users(self._key):
            self.initialize_users()

        self._consumer_threads: List[threading.Thread] = []
        self._start_consumer_threads()

    def __del__(self):
        dispatch(self.shutdown)

    def _start_consumer_threads(self):
        if not MarchHareConfig.is_enabled:
            log.warning("RabbitMQ is not enabled. Skipping consumer thread initialization.")
            return

        self._consumer_threads = [
            threading.Thread(target=self._consume_plugin_events, daemon=True)
        ]
        for thread in self._consumer_threads:
            thread.start()

    def _end_consumer_threads(self):
        for thread in self._consumer_threads:
            if thread.is_alive():
                thread.join(timeout=1)
        self._consumer_threads = []

    def _consume_plugin_events(self):
        """
        Consumer thread that listens for activation events from RabbitMQ.
        """
        def callback(ch, method, properties, body):
            """Handle the received message."""
            try:
                event = json.loads(body)

                if event.get("source_pod") == self._pod_id:
                    log.debug(f"Ignoring event with payload {event['payload']} from the same pod {self._pod_id}")
                    return

                if event["event_type"] == MarchHareConfig.events["PLUGIN_INSTALLATION"]:
                    payload = event["payload"]
                    self.plugin_manager.install_extracted_plugin(payload["plugin_id"], payload["plugin_path"])
                elif event["event_type"] == MarchHareConfig.events["PLUGIN_UNINSTALLATION"]:
                    payload = event["payload"]
                    self.plugin_manager.uninstall_plugin(payload["plugin_id"])
                else:
                    log.warning(f"Unknown event type: {event['event_type']}. Message body: {body}")
            except json.JSONDecodeError as e:
                log.error(f"Failed to decode JSON message: {e}. Message body: {body}")
            except Exception as e:
                log.error(f"Error processing message: {e}. Message body: {body}")

        self.march_hare.consume_event(callback, MarchHareConfig.channels["PLUGIN_EVENTS"])

    def _on_end_plugin_install(self, plugin_id: str, plugin_path: str):
        # activate the eventual custom endpoints
        for endpoint in self.plugin_manager.plugins[plugin_id].endpoints:
            endpoint.activate(self.fastapi_app)

        self._inform_cheshirecats_plugin(plugin_id, "install")

        # notify the RabbitMQ about the new plugin installed
        self.march_hare.notify_event(
            event_type=MarchHareConfig.events["PLUGIN_INSTALLATION"],
            payload={
                "plugin_id": plugin_id,
                "plugin_path": plugin_path
            },
            exchange=MarchHareConfig.channels["PLUGIN_EVENTS"],
        )

    def _on_start_plugin_uninstall(self, plugin_id: str):
        self._inform_cheshirecats_plugin(plugin_id, "uninstall")

    def _on_end_plugin_uninstall(self, plugin_id: str, endpoints: List[CustomEndpoint]):
        # deactivate the eventual custom endpoints
        for endpoint in endpoints:
            if endpoint.plugin_id == plugin_id:
                endpoint.deactivate(self.fastapi_app)

        # notify the RabbitMQ about the new uninstalled plugin
        self.march_hare.notify_event(
            event_type=MarchHareConfig.events["PLUGIN_UNINSTALLATION"],
            payload={"plugin_id": plugin_id},
            exchange=MarchHareConfig.channels["PLUGIN_EVENTS"],
        )

    def _on_finish_plugins_sync(self):
        # Store endpoints for later activation
        self._pending_endpoints = deepcopy(self.plugin_manager.endpoints)

        # If app is already available, activate immediately
        if self.fastapi_app is not None:
            self._activate_pending_endpoints()

    def _on_end_plugin_toggle(
        self, plugin_id: str, endpoints: List[CustomEndpoint], what: Literal["activated", "deactivated"]
    ):
        if what == "activated":
            return

        # deactivate the eventual custom endpoints
        for endpoint in endpoints:
            if endpoint.plugin_id == plugin_id:
                endpoint.deactivate(self.fastapi_app)

        self._inform_cheshirecats_plugin(plugin_id, "deactivated")

    def _activate_pending_endpoints(self):
        for endpoint in self._pending_endpoints:
            endpoint.activate(self.fastapi_app)
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

        self.embedder = get_factory_object(self._key, factory)
        self.embedder_name = get_embedder_name(self.embedder)

        # Get embedder size (langchain classes do not store it)
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

            raise LoadMemoryException(f"Load memory exception: {utils.explicit_error_message(e)}")

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

    def _inform_cheshirecats_plugin(
        self, plugin_id: str, what: Literal["install", "uninstall", "activated", "deactivated"]
    ):
        """
        Find the plugins for the given Cheshire Cat and update its plugin manager.

        Args:
            plugin_id: The id of the plugin to install or uninstall
            what: The action to perform, either "install" or "uninstall"

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """
        for ccat_id in crud.get_agents_main_keys():
            # on installation, it's enough to get the Cheshire Cat, it will load the plugin manager,
            # which will load the plugins
            ccat = self.get_cheshire_cat(ccat_id)
            if what in ["uninstall", "deactivated"]:
                # deactivate plugins in the Cheshire Cats
                ccat.plugin_manager.deactivate_plugin(plugin_id)

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
        await ccat.vector_memory_handler.initialize(self.embedder_name, self.embedder_size)

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
        if self.websocket_manager:
            await self.websocket_manager.close_all_connections()

        self._end_consumer_threads()

        self.core_auth_handler = None
        self.plugin_manager = None
        self.rabbit_hole = None
        self.embedder = None
        self.embedder_name = None
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
    def mad_hatter(self) -> MadHatter:
        return self.plugin_manager
