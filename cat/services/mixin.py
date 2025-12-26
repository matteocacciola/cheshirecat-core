from abc import ABC, abstractmethod
from typing import Dict
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.rabbit_hole import RabbitHole
from cat.services.factory.auth_handler import BaseAuthHandler
from cat.services.factory.chunker import BaseChunker
from cat.services.factory.file_manager import BaseFileManager
from cat.services.factory.vector_db import BaseVectorDatabaseHandler
from cat.services.service_provider import ServiceProvider


class ContextMixin(ABC):
    """
    Mixin for shared methods between all the classes managing settings of the agents.
    Provides access to chat request/response, user info, and core subsystems.
    """
    def __init__(self):
        self.service_provider = ServiceProvider(self.agent_key, self.mad_hatter)

    @property
    def embedder_name(self) -> str | None:
        return self.service_provider.get_nlp_object_name(self.embedder, "default_embedder")

    @property
    def embedder_size(self):
        return len(self.embedder.embed_query("hello world"))

    @property
    def mad_hatter(self) -> MadHatter:
        """
        Gives access to the `Tweedledee` plugin manager.

        Returns:
            mad_hatter (Tweedledee): Module to manage plugins.

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
    @abstractmethod
    def agent_key(self) -> str | None:
        """The agent's unique identifier, if applicable."""
        pass

    @property
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


class OrchestratorMixin(ContextMixin, ABC):
    """
    Mixin for shared methods for the orchestrator class.
    Provides access to chat request/response, user info, and core subsystems.
    """
    @property
    def embedder(self) -> Embeddings:
        return self.service_provider.get_embedder()


class BotMixin(ContextMixin, ABC):
    """
    Mixin for shared methods between StrayCat and CheshireCat.
    Provides access to chat request/response, user info, and core subsystems.
    """
    @property
    def lizard(self) -> "BillTheLizard":
        """
        Instance of `BillTheLizard`. Use it to access the main components of the Cat.

        Returns:
            lizard: BillTheLizard
                Instance of langchain `BillTheLizard`.
        """
        from cat.looking_glass.bill_the_lizard import BillTheLizard

        return BillTheLizard()

    @property
    def embedder(self) -> Embeddings:
        return self.lizard.embedder

    @property
    def large_language_model(self) -> BaseLanguageModel:
        return self.service_provider.get_large_language_model()

    @property
    def custom_auth_handler(self) -> BaseAuthHandler:
        return self.service_provider.get_custom_auth_handler()

    @property
    def file_manager(self) -> BaseFileManager:
        return self.service_provider.get_file_manager()

    @property
    def chunker(self) -> BaseChunker:
        return self.service_provider.get_chunker()

    @property
    def vector_memory_handler(self) -> BaseVectorDatabaseHandler:
        return self.service_provider.get_vector_memory_handler()

    @property
    def large_language_model_name(self) -> str | None:
        return self.service_provider.get_nlp_object_name(self.large_language_model, "default_llm")

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
    @property
    def file_handlers(self) -> Dict:
        return self.mad_hatter.execute_hook("rabbithole_instantiates_parsers", {}, caller=self)
