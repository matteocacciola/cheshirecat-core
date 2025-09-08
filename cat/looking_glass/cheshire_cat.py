from typing import Dict
from uuid import uuid4
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from cat.auth.auth_utils import hash_password, DEFAULT_USER_USERNAME
from cat.auth.permissions import get_base_permissions
from cat.db.cruds import (
    settings as crud_settings,
    history as crud_history,
    plugins as crud_plugins,
    users as crud_users,
)
from cat.env import get_env_bool
from cat.factory.auth_handler import AuthHandlerFactory
from cat.factory.auth_handler import BaseAuthHandler
from cat.factory.chunker import ChunkerFactory, BaseChunker
from cat.factory.file_manager import BaseFileManager, FileManagerFactory
from cat.factory.llm import LLMFactory
from cat.factory.vector_db import VectorDatabaseFactory, BaseVectorDatabaseHandler
from cat.log import log
from cat.mad_hatter import Tweedledee
from cat.utils import get_factory_object, get_updated_factory_object


# main class
class CheshireCat:
    """
    The Cheshire Cat.

    This is the main class that manages the whole AI application.
    It contains references to all the main modules and is responsible for the bootstrapping of the application.

    In most cases you will not need to interact with this class directly, but rather with class `StrayCat` which will be available in your plugin's hooks, tools, forms end endpoints.
    """
    def __init__(self, agent_id: str):
        """
        Cat initialization. At init time, the Cat executes the bootstrap.

        Notes
        -----
        Bootstrapping is the process of loading the plugins, the LLM, the memories.
        """
        self.id = agent_id

        # instantiate plugin manager (loads all plugins' hooks and tools)
        self.plugin_manager = Tweedledee(self.id)
        self.plugin_manager.find_plugins()

        # allows plugins to do something before cat components are loaded
        self.plugin_manager.execute_hook("before_cat_bootstrap", cat=self)

        self.large_language_model: BaseLanguageModel = get_factory_object(self.id, LLMFactory(self.plugin_manager))
        self.custom_auth_handler: BaseAuthHandler = get_factory_object(self.id, AuthHandlerFactory(self.plugin_manager))
        self.file_manager: BaseFileManager = get_factory_object(self.id, FileManagerFactory(self.plugin_manager))
        self.chunker: BaseChunker = get_factory_object(self.id, ChunkerFactory(self.plugin_manager))
        self.vector_memory_handler: BaseVectorDatabaseHandler = get_factory_object(
            self.id, VectorDatabaseFactory(self.plugin_manager)
        )
        self.vector_memory_handler.agent_id = self.id

        # Initialize the default user if not present
        if not crud_users.get_users(self.id):
            self.initialize_users()

        # allows plugins to do something after the cat bootstrap is complete
        self.plugin_manager.execute_hook("after_cat_bootstrap", cat=self)

    def __eq__(self, other: "CheshireCat") -> bool:
        """Check if two cats are equal."""
        if not isinstance(other, CheshireCat):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"CheshireCat(agent_id={self.id})"

    def __del__(self):
        """Cat destructor."""
        self.shutdown()

    def initialize_users(self):
        user_id = str(uuid4())

        crud_users.set_users(self.id, {
            user_id: {
                "id": user_id,
                "username": DEFAULT_USER_USERNAME,
                "password": hash_password(DEFAULT_USER_USERNAME),
                # user has minor permissions
                "permissions": get_base_permissions(),
            }
        })

    def shutdown(self) -> None:
        self.custom_auth_handler = None
        self.plugin_manager = None
        self.large_language_model = None
        self.file_manager = None
        self.chunker = None

    async def destroy_memory(self):
        """Destroy all data from the cat's memory."""
        log.info(f"Agent id: {self.id}. Destroying all data from the cat's memory")

        # destroy all memories
        await self.vector_memory_handler.destroy_all_points("declarative")

    async def destroy(self):
        """Destroy all data from the cat."""
        log.info(f"Agent id: {self.id}. Destroying all data from the cat")
        # destroy all memories
        await self.destroy_memory()

        self.shutdown()

        crud_settings.destroy_all(self.id)
        crud_history.destroy_all(self.id)
        crud_plugins.destroy_all(self.id)
        crud_users.destroy_all(self.id)

        # if Rabbit Hole storage is enabled, remove the folder from storage
        if get_env_bool("CCAT_RABBIT_HOLE_STORAGE_ENABLED") and self.file_manager is not None:
            self.file_manager.remove_folder_from_storage(self.id)

    def send_ws_message(self, content: str, msg_type="notification"):
        log.error(f"Agent id: {self.id}. No websocket connection open")

    def replace_llm(self, language_model_name: str, settings: Dict) -> Dict:
        """
        Replace the current LLM with a new one. This method is used to change the LLM of the cat.
        Args:
            language_model_name: name of the new LLM
            settings: settings of the new LLM

        Returns:
            The dictionary resuming the new name and settings of the LLM
        """
        factory = LLMFactory(self.plugin_manager)
        updater = get_updated_factory_object(self.id, factory, language_model_name, settings)

        try:
            # try to reload the llm of the cat
            self.large_language_model = get_factory_object(self.id, factory)
        except Exception as e:
            log.error(f"Agent id: {self.id}. Error while loading the new LLM: {e}")

            # something went wrong: rollback
            if updater.old_setting is not None:
                self.replace_llm(updater.old_setting["name"], updater.old_setting["value"])

            raise e

        return {"name": language_model_name, "value": updater.new_setting["value"]}

    def replace_auth_handler(self, auth_handler_name: str, settings: Dict) -> Dict:
        """
        Replace the current Auth Handler with a new one.
        Args:
            auth_handler_name: name of the new Auth Handler
            settings: settings of the new Auth Handler

        Returns:
            The dictionary resuming the new name and settings of the Auth Handler
        """
        factory = AuthHandlerFactory(self.plugin_manager)
        updater = get_updated_factory_object(self.id, factory, auth_handler_name, settings)

        self.custom_auth_handler = get_factory_object(self.id, factory)

        return {"name": auth_handler_name, "value": updater.new_setting["value"]}

    def replace_file_manager(self, file_manager_name: str, settings: Dict) -> Dict:
        """
        Replace the current file manager with a new one. This method is used to change the file manager of the lizard.

        Args:
            file_manager_name: name of the new file manager
            settings: settings of the new file manager

        Returns:
            The dictionary resuming the new name and settings of the file manager
        """
        factory = FileManagerFactory(self.plugin_manager)
        updater = get_updated_factory_object(self.id, factory, file_manager_name, settings)

        try:
            old_filemanager = self.file_manager

            # reload the file manager of the lizard
            self.file_manager = get_factory_object(self.id, factory)

            self.file_manager.transfer(old_filemanager, self.id)
        except Exception as e:
            log.error(f"Error while loading the new File Manager: {e}")

            # something went wrong: rollback
            if updater.old_setting is not None:
                self.replace_file_manager(updater.old_setting["name"], updater.old_setting["value"])

            raise e

        return {"name": file_manager_name, "value": updater.new_setting["value"]}

    def replace_chunker(self, chunker_name: str, settings: Dict) -> Dict:
        """
        Replace the current Auth Handler with a new one.
        Args:
            chunker_name: name of the new chunker
            settings: settings of the new chunker

        Returns:
            The dictionary resuming the new name and settings of the Auth Handler
        """
        factory = ChunkerFactory(self.plugin_manager)
        updater = get_updated_factory_object(self.id, factory, chunker_name, settings)

        self.chunker = get_factory_object(self.id, ChunkerFactory(self.plugin_manager))

        return {"name": chunker_name, "value": updater.new_setting["value"]}

    async def replace_vector_memory_handler(
        self, vector_memory_name: str, settings: Dict
    ) -> Dict:
        """
        Replace the current Vector Memory Handler with a new one.
        Args:
            vector_memory_name: name of the new Vector Memory Handler
            settings: settings of the new Vector Memory Handler

        Returns:
            The dictionary resuming the new name and settings of the Vector Memory Handler
        """
        factory = VectorDatabaseFactory(self.plugin_manager)
        updater = get_updated_factory_object(self.id, factory, vector_memory_name, settings)

        self.vector_memory_handler = get_factory_object(self.id, factory)

        lizard = self.lizard
        await self.vector_memory_handler.initialize(lizard.embedder_name, lizard.embedder_size)

        return {"name":vector_memory_name, "value": updater.new_setting["value"]}

    @property
    def lizard(self) -> "BillTheLizard":
        """
        Instance of langchain `BillTheLizard`. Use it to access the main components of the Cat.

        Returns:
            lizard: BillTheLizard
                Instance of langchain `BillTheLizard`.
        """
        from cat.looking_glass import BillTheLizard
        return BillTheLizard()

    @property
    def websocket_manager(self) -> "BillTheLizard":
        """
        Instance of `WebsocketManager`. Use it to access the manager of the Websocket connections.

        Returns:
            websocket_manager: WebsocketManager
                Instance of `WebsocketManager`.
        """
        return self.lizard.websocket_manager

    @property
    def embedder(self) -> Embeddings:
        """
        Langchain `Embeddings` object.
        Returns:
            embedder: Langchain `Embeddings`
                Langchain embedder to turn text into a vector.

        Examples
        --------
        >> cat.embedder.embed_query("Oh dear!")
        [0.2, 0.02, 0.4, ...]
        """
        return self.lizard.embedder

    @property
    def rabbit_hole(self) -> "RabbitHole":
        """
        Gives access to the `RabbitHole`, to upload documents and URLs into the vector DB.

        Returns:
            rabbit_hole: RabbitHole
            Module to ingest documents and URLs for RAG.
        Examples
        --------
        >> cat.rabbit_hole.ingest_file(...)
        """
        return self.lizard.rabbit_hole

    @property
    def core_auth_handler(self) -> "CoreAuthHandler":
        """
        Gives access to the `CoreAuthHandler` object. Use it to interact with the Cat's authentication handler.

        Returns:
            core_auth_handler: CoreAuthHandler
                Core authentication handler of the Cat
        """
        return self.lizard.core_auth_handler

    @property
    def mad_hatter(self) -> Tweedledee:
        """
        Gives access to the `Tweedledee` plugin manager.

        Returns:
            mad_hatter: Tweedledee
                Module to manage plugins.

        Examples
        --------
        Obtain the path in which your plugin is located
        >> cat.mad_hatter.get_plugin().path
        /app/plugins/my_plugin
        Obtain plugin settings
        >> cat.mad_hatter.get_plugin().load_settings()
        {"num_cats": 44, "rows": 6, "remainder": 0}
        """
        return self.plugin_manager

    # each time we access the file handlers, plugins can intervene
    @property
    def file_handlers(self) -> Dict:
        return self.plugin_manager.execute_hook("rabbithole_instantiates_parsers",  {}, cat=self)
