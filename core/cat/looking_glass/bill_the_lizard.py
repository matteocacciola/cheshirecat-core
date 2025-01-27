from typing import Dict
from uuid import uuid4
from langchain_core.embeddings import Embeddings
from fastapi import FastAPI

from cat import utils
from cat.adapters.factory_adapter import FactoryAdapter
from cat.agents.main_agent import MainAgent
from cat.auth.auth_utils import hash_password, DEFAULT_ADMIN_USERNAME
from cat.auth.permissions import get_full_admin_permissions
from cat.db import crud
from cat.db.cruds import settings as crud_settings, users as crud_users, plugins as crud_plugins
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.env import get_env
from cat.exceptions import LoadMemoryException
from cat.factory.base_factory import ReplacedNLPConfig
from cat.factory.custom_auth_handler import CoreAuthHandler
from cat.factory.custom_file_manager import BaseFileManager
from cat.factory.embedder import EmbedderFactory
from cat.factory.file_manager import FileManagerFactory
from cat.log import log
from cat.looking_glass.cheshire_cat import CheshireCat
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.tweedledum import Tweedledum
from cat.memory.utils import VectorEmbedderSize
from cat.memory.vector_memory_builder import VectorMemoryBuilder
from cat.rabbit_hole import RabbitHole
from cat.utils import singleton, get_embedder_name


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

        self.__key = DEFAULT_SYSTEM_KEY

        self.fastapi_app = None

        self.embedder: Embeddings | None = None
        self.embedder_name: str | None = None
        self.embedder_size: VectorEmbedderSize | None = None

        self.file_manager: BaseFileManager | None = None

        self.plugin_manager = Tweedledum()

        # load embedder
        self.load_language_embedder()

        # load file manager
        self.load_filemanager()

        # Rabbit Hole Instance
        self.rabbit_hole = RabbitHole()

        self.core_auth_handler = CoreAuthHandler()

        # Main agent instance (for reasoning)
        self.main_agent = MainAgent()

        self.plugin_manager.on_end_plugin_install_callback = self.on_end_plugin_install_callback
        self.plugin_manager.on_start_plugin_uninstall_callback = self.on_start_plugin_uninstall_callback
        self.plugin_manager.on_end_plugin_uninstall_callback = self.on_end_plugin_uninstall_callback

        # Initialize the default admin if not present
        if not crud_users.get_users(self.__key):
            self.initialize_users()

    def __del__(self):
        self.shutdown()

    def set_fastapi_app(self, app: FastAPI) -> "BillTheLizard":
        self.fastapi_app = app
        return self

    def on_end_plugin_install_callback(self):
        """
        Callback executed when a plugin is installed. It informs the Cheshire Cats about the new plugin available in the
        system. It also activates the endpoints of the plugin in the Mad Hatter.
        """

        for endpoint in self.endpoints:
            endpoint.activate(self.fastapi_app)

        for ccat_id in crud.get_agents_main_keys():
            ccat = self.get_cheshire_cat(ccat_id)

            # inform the Cheshire Cats about the new plugin available in the system
            ccat.plugin_manager.find_plugins()

    def on_start_plugin_uninstall_callback(self, plugin_id: str):
        """
        Clean up the plugin uninstallation. It removes the plugin settings from the database for the different agents.

        Args:
            plugin_id: The id of the plugin to remove
        """

        for ccat_id in crud.get_agents_main_keys():
            ccat = self.get_cheshire_cat(ccat_id)

            # deactivate plugins in the Cheshire Cats
            ccat.plugin_manager.deactivate_plugin(plugin_id)

    def on_end_plugin_uninstall_callback(self, plugin_id: str):
        for endpoint in self.endpoints:
            endpoint.deactivate()

        crud_plugins.destroy_plugin(plugin_id)

    async def reload_embed_procedures(self):
        """
        Reload the embedding of the procedures in the procedural memory for each Cheshire Cat.
        """

        for ccat_id in crud.get_agents_main_keys():
            ccat = self.get_cheshire_cat(ccat_id)

            # inform the Cheshire Cats about the new plugin available in the system
            await ccat.embed_procedures()

    def initialize_users(self):
        admin_id = str(uuid4())

        crud_users.set_users(self.__key, {
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

        selected_config = FactoryAdapter(factory).get_factory_config_by_settings(self.__key)

        self.embedder = factory.get_from_config_name(self.__key, selected_config["value"]["name"])
        self.embedder_name = get_embedder_name(self.embedder)

        # Get embedder size (langchain classes do not store it)
        embedder_size = len(self.embedder.embed_query("hello world"))
        self.embedder_size = VectorEmbedderSize(text=embedder_size)

    def load_filemanager(self):
        """
        Hook into the file manager selection. Allows to modify how the Lizard selects the file manager at bootstrap
        time.
        """

        factory = FileManagerFactory(self.plugin_manager)

        selected_config = FactoryAdapter(factory).get_factory_config_by_settings(self.__key)

        self.file_manager = factory.get_from_config_name(self.__key, selected_config["value"]["name"])

    async def replace_embedder(self, language_embedder_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current embedder with a new one. This method is used to change the embedder of the lizard.

        Args:
            language_embedder_name: name of the new embedder
            settings: settings of the new embedder

        Returns:
            The dictionary resuming the new name and settings of the embedder
        """

        adapter = FactoryAdapter(EmbedderFactory(self.plugin_manager))
        updater = adapter.upsert_factory_config_by_settings(self.__key, language_embedder_name, settings)

        # reload the embedder of the lizard
        self.load_language_embedder()

        try:
            await self.memory_builder.build()  # create new collections (different embedder!)
        except Exception as e:  # restore the original Embedder
            log.error(e)

            # something went wrong: rollback
            adapter.rollback_factory_config(self.__key)

            if updater.old_setting is not None:
                await self.replace_embedder(updater.old_setting["value"]["name"], updater.old_factory["value"])

            raise LoadMemoryException(f"Load memory exception: {utils.explicit_error_message(e)}")

        # recreate tools embeddings
        self.plugin_manager.find_plugins()

        await self.reload_embed_procedures()

        return ReplacedNLPConfig(name=language_embedder_name, value=updater.new_setting["value"])

    def replace_file_manager(self, file_manager_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current file manager with a new one. This method is used to change the file manager of the lizard.

        Args:
            file_manager_name: name of the new file manager
            settings: settings of the new file manager

        Returns:
            The dictionary resuming the new name and settings of the file manager
        """

        adapter = FactoryAdapter(FileManagerFactory(self.plugin_manager))
        updater = adapter.upsert_factory_config_by_settings(self.__key, file_manager_name, settings)

        try:
            old_filemanager = self.file_manager

            # reload the file manager of the lizard
            self.load_filemanager()

            self.file_manager.transfer(old_filemanager)
        except ValueError as e:
            log.error(f"Error while loading the new File Manager: {e}")

            # something went wrong: rollback
            adapter.rollback_factory_config(self.__key)

            if updater.old_setting is not None:
                self.replace_file_manager(updater.old_setting["value"]["name"], updater.new_setting["value"])

            raise e

        return ReplacedNLPConfig(name=file_manager_name, value=updater.new_setting["value"])

    def get_cheshire_cat(self, agent_id: str) -> CheshireCat | None:
        """
        Get the Cheshire Cat with the given id, directly from db.

        Args:
            agent_id: The id of the agent to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """

        if agent_id == DEFAULT_SYSTEM_KEY:
            raise ValueError(f"{DEFAULT_SYSTEM_KEY} is a reserved name for agents")

        if agent_id not in crud.get_agents_main_keys():
            return None

        return CheshireCat(agent_id)

    async def create_cheshire_cat(self, agent_id: str) -> CheshireCat:
        """
        Create the Cheshire Cat with the given id, directly from db.

        Args:
            agent_id: The id of the agent to get

        Returns:
            The Cheshire Cat with the given id, or None if it doesn't exist
        """

        if agent_id in [DEFAULT_SYSTEM_KEY]:
            raise ValueError(f"{DEFAULT_SYSTEM_KEY} is a reserved name for agents")

        if agent_id in crud.get_agents_main_keys():
            return self.get_cheshire_cat(agent_id)

        result = CheshireCat(agent_id)
        await result.embed_procedures()

        return result

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

    def shutdown(self) -> None:
        """
        Shuts down the Bill The Lizard Manager. It closes all the strays' connections and stops the scheduling system.

        Returns:
            None
        """

        self.core_auth_handler = None
        self.plugin_manager = None
        self.rabbit_hole = None
        self.main_agent = None
        self.embedder = None
        self.embedder_name = None
        self.embedder_size = None
        self.file_manager = None
        self.fastapi_app = None

    @property
    def config_key(self):
        return self.__key

    @property
    def mad_hatter(self) -> MadHatter:
        return self.plugin_manager

    @property
    def memory_builder(self) -> VectorMemoryBuilder:
        return VectorMemoryBuilder()

    @property
    def endpoints(self):
        if not self.fastapi_app:
            return []

        return [
            endpoint
            for endpoint in self.plugin_manager.endpoints
            if endpoint.plugin_id in self.plugin_manager.active_plugins
        ]
