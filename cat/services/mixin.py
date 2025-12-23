from abc import ABC, abstractmethod
from typing import Dict
from langchain_core.embeddings import Embeddings

from cat.looking_glass.tweedledee import Tweedledee
from cat.rabbit_hole import RabbitHole
from cat.services.websocket_manager import WebSocketManager
from cat.utils import get_nlp_object_name


class CatMixin(ABC):
    """
    Mixin for shared methods between StrayCat and BaseAgent.
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
    def websocket_manager(self) -> WebSocketManager:
        """
        Instance of `WebsocketManager`. Use it to access the manager of the Websocket connections.

        Returns:
            websocket_manager (WebsocketManager): Instance of `WebsocketManager`.
        """
        return self.lizard.websocket_manager

    @property
    def embedder(self) -> Embeddings:
        """
        Langchain `Embeddings` object.

        Returns:
            embedder: Langchain `Embeddings`. Langchain embedder to turn text into a vector.

        Examples
        --------
        >> cat.embedder.embed_query("Oh dear!")
        [0.2, 0.02, 0.4, ...]
        """
        return self.lizard.embedder

    @property
    def embedder_name(self) -> str | None:
        return self.lizard.embedder_name

    @property
    def large_language_model_name(self) -> str | None:
        if not hasattr(self, "large_language_model"):
            return None

        llm = getattr(self, "large_language_model")
        if llm is None:
            return None
        return get_nlp_object_name(llm, "default_llm")

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

    @property
    def mad_hatter(self) -> Tweedledee:
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
    def file_handlers(self) -> Dict:
        """The agent's file handlers, if applicable."""
        pass
