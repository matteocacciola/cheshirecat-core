import os
from io import BytesIO
from typing import Dict, List

from cat.db.cruds import (
    settings as crud_settings,
    conversations as crud_conversations,
    plugins as crud_plugins,
    users as crud_users,
)
from cat.log import log
from cat.looking_glass.humpty_dumpty import HumptyDumpty, subscriber
from cat.looking_glass.mad_hatter.procedures import CatProcedureType
from cat.looking_glass.models import StoredSourceWithMetadata
from cat.looking_glass.tweedledee import Tweedledee
from cat.services.memory.models import VectorMemoryType, Record
from cat.services.mixin import BotMixin
from cat.utils import guess_file_type, is_url


# main class
class CheshireCat(BotMixin):
    """
    The Cheshire Cat.

    This is the main class that manages the whole AI application.
    It contains references to all the main modules and is responsible for the bootstrapping of the application.

    In most cases you will not need to interact with this class directly, but rather with class `StrayCat` which will be
    available in your plugin's hooks, tools, forms end endpoints.
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
        self._id = agent_id

        self.dispatcher = HumptyDumpty()
        self.dispatcher.subscribe_from(self)

        # instantiate plugin manager (loads all plugins' hooks and tools)
        self.plugin_manager = Tweedledee(self._id)
        self.plugin_manager.discover_plugins()

        # allows plugins to do something before cat components are loaded
        self.plugin_manager.execute_hook("before_cat_bootstrap", caller=self)

        # bootstrap cat
        super().__init__()

        # Initialize the default user if not present
        if not crud_users.get_users(self._id):
            crud_users.initialize_empty_users(self._id)

        # allows plugins to do something after the cat bootstrap is complete
        self.plugin_manager.execute_hook("after_cat_bootstrap", caller=self)

    def __eq__(self, other: "CheshireCat") -> bool:
        """Check if two cats are equal."""
        if not isinstance(other, CheshireCat):
            return False
        return self._id == other.agent_key

    def __hash__(self) -> int:
        return hash(self._id)

    def __repr__(self) -> str:
        return f"CheshireCat(agent_id={self._id})"

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
        log.info(f"Agent id: {self._id}. Destroying all data from the cat's memory")

        # destroy all memories
        for collection_name in await self.vector_memory_handler.get_collection_names():
            await self.vector_memory_handler.delete_tenant_points(collection_name)

    async def destroy(self):
        """Destroy all data from the cat."""
        log.info(f"Agent id: {self._id}. Destroying all data from the cat")

        # destroy all memories
        await self.destroy_memory()

        # remove the folder from storage
        self.file_manager.remove_folder_from_storage(self._id)

        self.shutdown()

        crud_settings.destroy_all(self._id)
        crud_conversations.destroy_all(self._id)
        crud_plugins.destroy_all(self._id)
        crud_users.destroy_all(self._id)

    async def get_stored_sources_with_metadata(self) -> List[StoredSourceWithMetadata]:
        """Get all stored files with their metadata."""
        async def get_stored_source(point: Record) -> StoredSourceWithMetadata | None:
            metadata = point.payload.get("metadata", {})
            filename = metadata.get("source")
            if not filename:
                return None
            if is_url(filename):
                return StoredSourceWithMetadata(name=filename, content=None, metadata=metadata)
            file_content = self.file_manager.read_file(filename, self.agent_key)
            if not file_content:
                return None
            return StoredSourceWithMetadata(name=filename, content=BytesIO(file_content), metadata=metadata)

        collection_name = str(VectorMemoryType.DECLARATIVE)
        points, _ = await self.vector_memory_handler.get_all_tenant_points(collection_name, with_vectors=False)

        return list({
            stored_source
            for point in points
            if (stored_source := await get_stored_source(point))
        })

    async def embed_procedures(self):
        # Easy access to active procedures in plugin_manager (source of truth!)
        payloads = []
        vectors = []
        for ap in self.plugin_manager.procedures:
            # we don't want to embed MCP clients' procedures, because we want to always use the latest version
            if ap.type == CatProcedureType.MCP:
                continue

            if ap.type != CatProcedureType.TOOL:
                ap = ap()

            for t in ap.to_document_recall():
                payloads.append(t.document.model_dump())
                vectors.append(self.lizard.embedder.embed_query(t.document.page_content))

        if not payloads:
            return

        log.info(f"Agent id: {self._id}. Embedding procedures in vector memory")
        collection_name = str(VectorMemoryType.PROCEDURAL)

        # first, clear all existing procedural embeddings
        await self.vector_memory_handler.delete_tenant_points(collection_name)

        await self.vector_memory_handler.add_points_to_tenant(
            collection_name=collection_name, payloads=payloads, vectors=vectors,
        )
        log.info(f"Agent id: {self._id}. Embedded {len(payloads)} triggers in {collection_name} vector memory")

    async def embed_stored_sources(self, stored_sources: List[StoredSourceWithMetadata]):
        """Embeds stored sources in the vector memory"""
        if not stored_sources:
            return

        log.info(f"Agent id: {self._id}. Embedding stored files in vector memory")
        collection_name = str(VectorMemoryType.DECLARATIVE)

        # first, clear all existing declarative embeddings
        await self.vector_memory_handler.delete_tenant_points(collection_name)

        rabbit_hole = self.rabbit_hole
        for source in stored_sources:
            content_type = None
            if source.content:
                content_type, _ = guess_file_type(source.content)

            await rabbit_hole.ingest_file(
                cat=self,
                file=source.content or source.name,
                filename=source.name,
                metadata=source.metadata,
                store_file=False,
                content_type=content_type,
            )

        log.info(f"Agent id: {self._id}. Embedded {len(stored_sources)} files in {collection_name} vector memory")

    async def embed_all(self, stored_sources: List[StoredSourceWithMetadata]):
        """
        Re-embeds all the stored files and procedures in the vector memory.
        1. Re-initialize the vector memory handler with the current embedder
        2. Re-embed all the stored files
        3. Re-embed all the procedures

        Args:
            stored_sources (List[StoredFileWithMetadata]): The list of stored sources of the Knowledge Base, with metadata to embed.

        Notes
        -----
        This method is typically called when the embedder configuration changes to ensure that all embeddings are
        updated to use the new embedder. That's why the `stored_sources` are passed as argument, to avoid race
        conditions when multiple agents are updating their embedder at the same time on the same database.
        """
        # re-embed all the stored files
        await self.embed_stored_sources(stored_sources)

        # re-embed all the procedures
        await self.embed_procedures()

    def save_file(self, file_path: str, source: str, chat_id: str | None):
        """Saves a file to the cat's storage.
        Args:
            file_path (str): The path to the file to save.
            source (str): The source of the file.
            chat_id (str | None): The chat id associated with the file.
        """
        remote_root_dir = self.agent_key
        if chat_id:
            remote_root_dir = os.path.join(remote_root_dir, chat_id)

        self.file_manager.upload_file_to_storage(file_path, remote_root_dir, source)

    @subscriber("on_end_plugin_activate")
    async def on_end_plugin_activate(self, plugin_id: str) -> None:
        # Destroy all procedural embeddings
        await self.vector_memory_handler.delete_tenant_points(str(VectorMemoryType.PROCEDURAL))
        await self.embed_procedures()

    @subscriber("on_end_plugin_deactivate")
    async def on_end_plugin_deactivate(self, plugin_id: str) -> None:
        # Destroy all procedural embeddings
        await self.vector_memory_handler.delete_tenant_points(str(VectorMemoryType.PROCEDURAL))
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
        return self._id
