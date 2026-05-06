from abc import ABC, abstractmethod
from typing import Type, List
from pydantic import ConfigDict

from cat.services.factory.models import BaseFactoryConfigModel
from cat.services.factory.vector_db import BaseVectorDatabaseHandler
from cat.services.memory.models import VectorMemoryType, RecallSettings, DocumentRecall


class BaseContextRetriever(ABC):
    """
    Base class to build custom context retrievers. This class is used to create custom retrievers that can be used
    to retrieve the context from the vector database.
    MUST be implemented by subclasses.
    """
    def __init__(self):
        self._vector_memory_handler = None

    @property
    def vector_memory_handler(self) -> BaseVectorDatabaseHandler:
        return self._vector_memory_handler  # type: ignore[return-value]

    @vector_memory_handler.setter
    def vector_memory_handler(self, vmh: BaseVectorDatabaseHandler):
        self._vector_memory_handler = vmh  # type: ignore[assignment]

    @abstractmethod
    async def run(
        self,
        collection: VectorMemoryType,
        params: RecallSettings,
    ) -> List[DocumentRecall]:
        """
        Abstract method to recall relevant documents from a specified vector memory
        collection based on the given query vector. This method operates asynchronously.

        Args:
            collection (VectorMemoryType): The collection from which documents will be recalled.
            params (RecallSettings): The settings containing the query vector and other recall parameters.

        Returns:
            List[DocumentRecall]: A list of recalled documents along with their similarity scores.
        """
        pass


class DefaultContextRetriever(BaseContextRetriever):
    async def run(
        self,
        collection: VectorMemoryType,
        params: RecallSettings,
    ) -> List[DocumentRecall]:
        if params.k:
            memories = await self.vector_memory_handler.recall_tenant_memory_from_embedding(
                str(collection), params.embedding, params.metadata, params.k, params.threshold
            )
            return memories

        memories = await self.vector_memory_handler.recall_tenant_memory(str(collection))
        return memories


class ContextRetrieverSettings(BaseFactoryConfigModel, ABC):
    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type[BaseContextRetriever]:
        return BaseContextRetriever

    @classmethod
    @abstractmethod
    def pyclass(cls) -> Type[BaseContextRetriever]:
        pass


class DefaultContextRetrieverSettings(ContextRetrieverSettings):
    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Default context retriever",
            "description": "Configuration for the default context retriever",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[DefaultContextRetriever]:
        return DefaultContextRetriever
