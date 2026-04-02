from abc import ABC, abstractmethod
from typing import Dict

from cat.core_plugins.white_rabbit.white_rabbit import WhiteRabbit
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.rabbit_hole import RabbitHole
from cat.services.factory.agentic_workflow import BaseAgenticWorkflowHandler
from cat.services.factory.auth_handler import BaseAuthHandler
from cat.services.factory.chunker import BaseChunker
from cat.services.factory.embedder import Embeddings
from cat.services.factory.file_manager import BaseFileManager
from cat.services.factory.llm import LargeLanguageModel
from cat.services.factory.vector_db import BaseVectorDatabaseHandler
from cat.services.service_provider import ServiceProvider


class ContextMixin(ABC):
    """
    Mixin for shared methods between all the classes managing settings of the agents.
    Provides access to chat request/response, user info, and core subsystems.
    """
    _white_rabbit: WhiteRabbit = None
    _service_provider: ServiceProvider = None

    @property
    def service_provider(self):
        if not self._service_provider:
            self._service_provider = ServiceProvider(self.agent_key, self.mad_hatter)  # type: ignore[arg-type]
        return self._service_provider

    @property
    def mad_hatter(self) -> MadHatter:
        """
        Gives access to the `MadHatter` plugin manager.

        Returns:
            mad_hatter (MadHatter): Module to manage plugins.

        Examples
        --------
        Obtain the path in which your plugin is located
        >> cat.mad_hatter.get_plugin().path
        /app/cat/plugins/my_plugin
        Obtain plugin settings
        >> cat.mad_hatter.get_plugin().load_settings()
        {"num_cats": 44, "rows": 6, "remainder": 0}
        """
        return getattr(self, "plugin_manager")

    @property
    def white_rabbit(self) -> WhiteRabbit:
        return self._white_rabbit

    @white_rabbit.setter
    def white_rabbit(self, white_rabbit: WhiteRabbit):
        if self._white_rabbit is None:
            self._white_rabbit = white_rabbit

    @property
    @abstractmethod
    def agent_key(self) -> str | None:
        """The agent's unique identifier, if applicable."""
        pass

    @abstractmethod
    def embedder(self) -> Embeddings:
        """
        Langchain `Embeddings` object.

        Returns:
            embedder: Langchain `Embeddings`. Langchain embedder to turn text into a vector.

        Examples
        --------
        >> cat.lizard.embedder.embed_query("Oh dear!")
        [0.2, 0.02, 0.4, ...]
        """
        pass

    @abstractmethod
    async def toggle_plugin(self, plugin_id: str):
        """
        Toggles the state of a plugin with the given ID.

        Args:
            plugin_id (str): The unique identifier of the plugin to be toggled.
        """
        pass

    @abstractmethod
    async def bootstrap(self):
        """
        Abstract method to initialize and set up necessary configurations or resources.

        This method is intended to be overridden by subclasses to implement the specific
        bootstrap logic essential for their functionality.

        Raises:
            NotImplementedError: If the subclass does not implement the bootstrap logic.
        """
        pass


class OrchestratorMixin(ContextMixin, ABC):
    """
    Mixin for shared methods for the orchestrator class.
    Provides access to chat request/response, user info, and core subsystems.
    """
    async def embedder(self) -> Embeddings:
        return await self.service_provider.get_embedder()


class BotMixin(ContextMixin, ABC):
    """
    Mixin for shared methods between StrayCat and CheshireCat.
    Provides access to chat request/response, user info, and core subsystems.
    """
    @property
    def lizard(self) -> "BillTheLizard":  # type: ignore[name-defined]
        """
        Instance of `BillTheLizard`. Use it to access the main components of the Cat.

        Returns:
            lizard: BillTheLizard
                Instance of langchain `BillTheLizard`.
        """
        from cat.looking_glass.bill_the_lizard import BillTheLizard

        return BillTheLizard()

    async def embedder(self) -> Embeddings:
        return await self.lizard.embedder()

    async def large_language_model(self) -> LargeLanguageModel:
        return await self.service_provider.get_large_language_model()

    async def custom_auth_handler(self) -> BaseAuthHandler:
        return await self.service_provider.get_custom_auth_handler()

    async def file_manager(self) -> BaseFileManager:
        return await self.service_provider.get_file_manager()

    async def chunker(self) -> BaseChunker:
        return await self.service_provider.get_chunker()

    async def vector_memory_handler(self) -> BaseVectorDatabaseHandler:
        return await self.service_provider.get_vector_memory_handler()

    async def agentic_workflow(self) -> BaseAgenticWorkflowHandler:
        return await self.service_provider.get_agentic_workflow()

    @property
    def rabbit_hole(self) -> RabbitHole:
        """
        Gives access to the `RabbitHole`, to upload documents and URLs into the vector DB.

        Returns:
            rabbit_hole (RabbitHole): Module to ingest documents and URLs for RAG.

        Examples
        --------
        >> cat.rabbit_hole.ingest_file(...)
        """
        return self.lizard.rabbit_hole

    # each time we access the file handlers, plugins can intervene
    async def file_handlers(self) -> Dict:
        return await self.mad_hatter.execute_hook("rabbithole_instantiates_parsers", {}, caller=self)
