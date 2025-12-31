from typing import Dict

from cat.db.cruds import (
    settings as crud_settings,
    conversations as crud_conversations,
    plugins as crud_plugins,
    users as crud_users,
)
from cat.log import log
from cat.looking_glass.humpty_dumpty import HumptyDumpty, subscriber
from cat.looking_glass.mad_hatter.decorators.tool import CatTool
from cat.looking_glass.tweedledee import Tweedledee
from cat.services.memory.utils import VectorMemoryType
from cat.services.mixin import BotMixin


# main class
class CheshireCat(BotMixin):
    """
    The Cheshire Cat.

    This is the main class that manages the whole AI application.
    It contains references to all the main modules and is responsible for the bootstrapping of the application.

    In most cases you will not need to interact with this class directly, but rather with class `StrayCat` which will be available in your plugin's hooks, tools, forms end endpoints.
    """
    def __init__(self, agent_id: str):
        """
        Cat initialization. At init time, the Cat executes the bootstrap.

        Args:
            agent_id: The agent identifier

        Notes
        -----
        Bootstrapping is the process of loading the plugins, the LLM, the memories.
        """
        self.id = agent_id

        self.dispatcher = HumptyDumpty()
        self.dispatcher.subscribe_from(self)

        # instantiate plugin manager (loads all plugins' hooks and tools)
        self.plugin_manager = Tweedledee(self.id)
        self.plugin_manager.discover_plugins()

        # allows plugins to do something before cat components are loaded
        self.plugin_manager.execute_hook("before_cat_bootstrap", caller=self)

        # bootstrap cat
        super().__init__()

        # Initialize the default user if not present
        if not crud_users.get_users(self.id):
            crud_users.initialize_empty_users(self.id)

        # allows plugins to do something after the cat bootstrap is complete
        self.plugin_manager.execute_hook("after_cat_bootstrap", caller=self)

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

    def bootstrap_services(self):
        self.service_provider.bootstrap_services_bot()

    def shutdown(self) -> None:
        self.dispatcher.unsubscribe_from(self)

        self.plugin_manager = None

    async def destroy_memory(self):
        """Destroy all data from the cat's memory."""
        log.info(f"Agent id: {self.id}. Destroying all data from the cat's memory")

        # destroy all memories
        await self.vector_memory_handler.destroy_all_tenant_points(str(VectorMemoryType.DECLARATIVE))

    async def destroy(self):
        """Destroy all data from the cat."""
        log.info(f"Agent id: {self.id}. Destroying all data from the cat")

        # destroy all memories
        await self.destroy_memory()

        # remove the folder from storage
        self.file_manager.remove_folder_from_storage(self.id)

        self.shutdown()

        crud_settings.destroy_all(self.id)
        crud_conversations.destroy_all(self.id)
        crud_plugins.destroy_all(self.id)
        crud_users.destroy_all(self.id)

    async def embed_procedures(self):
        log.info(f"Agent id: {self.id}. Embedding procedures in vector memory")

        lizard = self.lizard
        await self.vector_memory_handler.initialize(lizard.embedder_name, lizard.embedder_size)

        # Destroy all procedural embeddings
        collection_name = str(VectorMemoryType.PROCEDURAL)
        await self.vector_memory_handler.destroy_all_tenant_points(collection_name)

        # Easy access to active procedures in plugin_manager (source of truth!)
        payloads = []
        vectors = []
        for ap in self.plugin_manager.procedures:
            if not isinstance(ap, CatTool):
                ap = ap()

            for t in ap.to_document_recall():
                payloads.append(t.document.model_dump())
                vectors.append(self.lizard.embedder.embed_query(t.document.page_content))

        await self.vector_memory_handler.add_points_to_tenant(collection_name=collection_name, payloads=payloads, vectors=vectors)
        log.info(f"Agent id: {self.id}. Embedded {len(payloads)} triggers in {collection_name} vector memory")

    @subscriber("on_end_plugin_activate")
    async def on_end_plugin_activate(self, plugin_id: str) -> None:
        await self.embed_procedures()

    @subscriber("on_end_plugin_deactivate")
    async def on_end_plugin_deactivate(self, plugin_id: str) -> None:
        await self.embed_procedures()

    # each time we access the file handlers, plugins can intervene
    @property
    def file_handlers(self) -> Dict:
        return self.plugin_manager.execute_hook("rabbithole_instantiates_parsers", {}, caller=self)

    @property
    def agent_key(self) -> str:
        """
        The unique identifier of the cat.

        Returns:
            agent_id (str): The unique identifier of the cat.
        """
        return self.id
