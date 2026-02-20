import asyncio
import mimetypes
import os
import tempfile
import uuid
from io import BytesIO
from typing import Dict, List, Callable

from cat.auth.permissions import AuthUserInfo
from cat.db.cruds import (
    settings as crud_settings,
    conversations as crud_conversations,
    plugins as crud_plugins,
    users as crud_users,
)
from cat.log import log
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.looking_glass.mad_hatter.procedures import CatProcedureType
from cat.looking_glass.models import StoredSourceWithMetadata
from cat.looking_glass.stray_cat import StrayCat
from cat.services.memory.models import VectorMemoryType, PointStruct
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

        # instantiate plugin manager (loads all plugins' hooks and tools)
        self.plugin_manager = MadHatter(self.agent_key)
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
        self.file_manager.remove_folder(self._id)

        self.shutdown()

        crud_settings.destroy_all(self._id)
        crud_conversations.destroy_all(self._id)
        crud_plugins.destroy_all(self._id)
        crud_users.destroy_all(self._id)

    async def get_stored_sources_with_metadata(self) -> Dict[VectorMemoryType, List[StoredSourceWithMetadata]]:
        """Get all stored files with their metadata."""
        results = {
            VectorMemoryType.DECLARATIVE: set(),
            VectorMemoryType.EPISODIC: set(),
        }
        for collection_name in results.keys():
            points, _ = await self.vector_memory_handler.get_all_tenant_points(str(collection_name), with_vectors=False)
            for point in points:
                metadata = point.payload.get("metadata", {})
                filename = metadata.get("source")
                if not filename:
                    continue

                if is_url(filename):
                    results[collection_name].add(
                        StoredSourceWithMetadata(name=filename, content=None, metadata=metadata, path=filename)
                    )
                    continue

                file_path = self.agent_key
                if chat_id := metadata.get("chat_id"):
                    file_path = os.path.join(file_path, chat_id)

                file_content = self.file_manager.read_file(filename, file_path)
                if not file_content:
                    continue

                results[collection_name].add(
                    StoredSourceWithMetadata(
                        name=filename, content=BytesIO(file_content), metadata=metadata, path=file_path,
                    )
                )

        return {k: list(v) for k, v in results.items()}

    async def embed_procedures(self, pt: CatProcedureType | None = None):
        points = [
            PointStruct(
                id=uuid.uuid4().hex,
                payload=t.document.model_dump(),
                vector=self.lizard.embedder.embed_query(t.document.page_content),
            ) for p in self.plugin_manager.procedures for t in p.to_document_recall() if pt is None or p.type == pt
        ]
        if not points:
            return

        log.info(f"Agent id: {self._id}. Embedding procedures in vector memory")
        collection_name = str(VectorMemoryType.PROCEDURAL)

        # first, clear all existing procedural embeddings
        await self.vector_memory_handler.delete_tenant_points(collection_name)

        await self.vector_memory_handler.add_points_to_tenant(collection_name=collection_name, points=points)
        log.info(f"Agent id: {self._id}. Embedded {len(points)} triggers in {collection_name} vector memory")

    async def _embed_stored_sources(
        self, collection_name: VectorMemoryType, stored_sources: List[StoredSourceWithMetadata]
    ):
        """
        Embeds stored sources into a vector memory collection.

        This method retrieves and processes a list of stored sources with their associated metadata and incorporates
        them into a vector memory collection. During this process, any pre-existing embeddings in the collection are
        cleared, and files are systematically ingested. The method handles potential irregularities such as missing
        content or stray references and logs appropriate messages.

        Args:
            collection_name (VectorMemoryType): The name of the collection where the stored sources
                will be embedded in vector memory.
            stored_sources (List[StoredSourceWithMetadata]): A list of sources, each containing content
                and metadata, to be embedded into vector memory.

        Raises:
            This method does not explicitly raise any exceptions but relies on the calling context to
            handle exceptions raised by dependent operations such as file ingestion.
        """
        log.info(f"Agent id: {self._id}. Embedding stored files to the vector memory")

        # first, clear all existing declarative and episodic embeddings
        await self.vector_memory_handler.delete_tenant_points(str(collection_name))

        rabbit_hole = self.rabbit_hole
        counter = 0
        for source in stored_sources:
            content_type = None
            if source.content:
                content_type, _ = guess_file_type(source.content)

            cat = self
            if chat_id := source.metadata.get("chat_id"):
                if not (stray_cat := self._find_stray_cat(chat_id)):
                    log.warning(f"Stray cat with id {chat_id} not found. Skipping file {source.path}")
                    continue

                cat = stray_cat

            await rabbit_hole.ingest_file(
                cat=cat,
                file=source.content or source.name,
                filename=source.name,
                metadata=source.metadata or {},
                store_file=False,
                content_type=content_type,
            )
            counter += 1

        log.info(f"Agent id: {self._id}. Embedded {counter} files to the vector memory")

    async def embed_all(self, stored_sources: Dict[VectorMemoryType, List[StoredSourceWithMetadata]]):
        """
        Re-embeds all the stored files and procedures in the vector memory.
        1. Re-initialize the vector memory handler with the current embedder
        2. Re-embed all the stored files
        3. Re-embed all the procedures

        Args:
            stored_sources (Dict[VectorMemoryType, List[StoredSourceWithMetadata]]): The list of stored sources of the
                Knowledge Base, with metadata to embed, grouped by collection.

        Notes
        -----
        This method is typically called when the embedder configuration changes to ensure that all embeddings are
        updated to use the new embedder. That's why the `stored_sources` are passed as argument, to avoid race
        conditions when multiple agents are updating their embedder at the same time on the same database.
        """
        # re-embed all the stored files
        tasks = []

        for collection_name, sources in stored_sources.items():
            if sources:
                tasks.append(self._embed_stored_sources(collection_name, sources))

        tasks.append(self.embed_procedures())

        # This allows concurrent embedding within each cat
        await asyncio.gather(*tasks)

    def save_file(self, file_bytes: bytes, content_type: str, source: str, chat_id: str | None = None):
        """
        Save file to the remote storage handled by the CheshireCat's file manager.

        Args:
            file_bytes (bytes): The file bytes to be saved.
            content_type (str): The content type of the file.
            source (str): The source of the file, i.e., the name used to store the file in the file manager.
            chat_id (str | None): The chat id of the stray cat, if any.
        """
        # save a file in a temporary folder
        extension = mimetypes.guess_extension(content_type)
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            temp_file.write(file_bytes)
            file_path = temp_file.name

        # upload a file to CheshireCat's file manager
        try:
            remote_root_dir = self.agent_key
            if chat_id:
                remote_root_dir = os.path.join(remote_root_dir, chat_id)

            self.file_manager.upload_file(file_path, remote_root_dir, source)
        except Exception as e:
            log.error(f"Error while uploading file {file_path}: {e}")
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    async def toggle_plugin(self, plugin_id: str):
        self.plugin_manager.toggle_plugin(plugin_id)

        # destroy all procedural embeddings and re-embed them
        await self.vector_memory_handler.delete_tenant_points(str(VectorMemoryType.PROCEDURAL))
        await self.embed_procedures()

        self.plugin_manager.execute_hook("after_plugin_toggling_on_agent", plugin_id, caller=self)

    def _find_stray_cat(self, chat_id: str) -> StrayCat | None:
        """Finds a stray cat by chat id.

        Args:
            chat_id (str): The chat id of the stray cat.

        Returns:
            StrayCat | None: The stray cat if found, None otherwise.
        """
        # look for an existing conversation with the id = chat_id
        user_id = crud_conversations.get_user_id_from_conversation_keys(self.agent_key, chat_id)
        if not user_id:
            return None

        user = crud_users.get_user(self.agent_key, user_id)
        if not user:
            return None

        return StrayCat(
            agent_id=self.agent_key,
            user_data=AuthUserInfo(**user),
            plugin_manager_generator=self.plugin_manager_generator,
            stray_id=chat_id,
        )

    def has_custom_endpoint(self, path: str, methods: set[str] | List[str] | None = None):
        """
        Check if an endpoint with the given path and methods exists in the active plugins.

        Args:
            path (str): The path of the endpoint to check.
            methods (set[str] | List[str] | None): The HTTP methods of the endpoint to check. If None, checks all methods.

        Returns:
            bool: True if the endpoint exists, False otherwise.
        """
        for plugin in self.plugin_manager.plugins.values():
            # Check if the plugin has an endpoint with the given path and methods
            for ep in plugin.endpoints:
                if ep.real_path == path and (methods is None or set(ep.methods) == set(methods)):
                    return True

        return False

    def plugin_exists(self, plugin_id: str):
        return plugin_id in self.plugin_manager.plugins.keys()

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

    @property
    def plugin_manager_generator(self) -> Callable[[], MadHatter]:
        return lambda: self.plugin_manager
