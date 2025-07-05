from abc import ABC
from typing import Type, List
from pydantic import ConfigDict

from cat.factory.base_factory import BaseFactory, BaseFactoryConfigModel
from cat.factory.custom_vector_db import BaseVectorDatabaseHandler, QdrantHandler


class VectorDatabaseSettings(BaseFactoryConfigModel, ABC):
    save_memory_snapshots: bool = False

    # class instantiating the model
    _pyclass: Type[BaseVectorDatabaseHandler] = None

    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type:
        return BaseVectorDatabaseHandler


class QdrantConfig(VectorDatabaseSettings):
    host: str = "cheshire_cat_vector_memory"
    port: int = 6333
    api_key: str | None = None
    client_timeout: int | None = 100

    _pyclass: Type = QdrantHandler

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Remote Qdrant Vector Database",
            "description": "Configuration for Remote Qdrant Vector Database",
            "link": "",
        }
    )


class VectorDatabaseFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[VectorDatabaseSettings]]:
        list_vector_db_default = [QdrantConfig]

        list_vector_dbs = self._hook_manager.execute_hook(
            "factory_allowed_vector_databases", list_vector_db_default, cat=None
        )
        return list_vector_dbs

    @property
    def setting_name(self) -> str:
        return "vector_database_selected"

    @property
    def setting_category(self) -> str:
        return "vector_database"

    @property
    def setting_factory_category(self) -> str:
        return "vector_database_factory"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return QdrantConfig

    @property
    def schema_name(self) -> str:
        return "vectorDatabaseName"
