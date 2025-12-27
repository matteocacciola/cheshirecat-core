from typing import Any, Dict, Callable
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel

from cat.db import models
from cat.db.cruds import settings as crud_settings
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.services.factory.auth_handler import BaseAuthHandler
from cat.services.service_factory import ServiceFactory
from cat.services.factory.chunker import BaseChunker
from cat.services.factory.file_manager import BaseFileManager
from cat.services.factory.vector_db import BaseVectorDatabaseHandler


class ServiceProvider:
    def __init__(self, agent_key: str, plugin_manager: MadHatter):
        self._agent_key = agent_key
        self._plugin_manager = plugin_manager

    def get_factory_object(self, factory: ServiceFactory) -> Any:
        if not (selected_config := crud_settings.get_settings_by_category(self._agent_key, factory.setting_category)):
            # if no config is saved, use default one and save to db
            # create the settings for the factory
            crud_settings.upsert_setting_by_name(
                self._agent_key,
                models.Setting(
                    name=factory.default_config_class.__name__,
                    category=factory.setting_category,
                    value=factory.default_config,
                ),
            )

            # reload from db and return
            selected_config = crud_settings.get_settings_by_category(self._agent_key, factory.setting_category)

        return factory.get_from_config_name(self._agent_key, selected_config["name"])

    def get_nlp_object_name(self, nlp_object: Any, default: str) -> str:
        name = default
        if hasattr(nlp_object, "repo_id"):
            name = nlp_object.repo_id
        elif hasattr(nlp_object, "model_path"):
            name = nlp_object.model_path
        elif hasattr(nlp_object, "model_name"):
            name = nlp_object.model_name
        elif hasattr(nlp_object, "model"):
            name = nlp_object.model

        replaces = ["/", "-", "."]
        for v in replaces:
            name = name.replace(v, "_")

        return name.lower()

    def get_embedder(self) -> Embeddings:
        return self.get_factory_object(ServiceFactory(
            self._plugin_manager,
            factory_allowed_handler_name="factory_allowed_embedders",
            setting_category="embedder",
            schema_name="languageEmbedderName",
        ))

    def get_large_language_model(self) -> BaseLanguageModel:
        return self.get_factory_object(ServiceFactory(
            self._plugin_manager,
            factory_allowed_handler_name="factory_allowed_llms",
            setting_category="llm",
            schema_name="languageModelName",
        ))

    def get_custom_auth_handler(self) -> BaseAuthHandler:
        return self.get_factory_object(ServiceFactory(
            self._plugin_manager,
            factory_allowed_handler_name="factory_allowed_auth_handlers",
            setting_category="auth_handler",
            schema_name="authorizatorName",
        ))

    def get_file_manager(self) -> BaseFileManager:
        return self.get_factory_object(ServiceFactory(
            self._plugin_manager,
            factory_allowed_handler_name="factory_allowed_file_managers",
            setting_category="file_manager",
            schema_name="fileManagerName",
        ))

    def get_chunker(self) -> BaseChunker:
        return self.get_factory_object(ServiceFactory(
            self._plugin_manager,
            factory_allowed_handler_name="factory_allowed_chunkers",
            setting_category="chunker",
            schema_name="chunkerName",
        ))

    def get_vector_memory_handler(self) -> BaseVectorDatabaseHandler:
        vector_memory_handler: BaseVectorDatabaseHandler = self.get_factory_object(ServiceFactory(
            self._plugin_manager,
            factory_allowed_handler_name="factory_allowed_vector_databases",
            setting_category="vector_database",
            schema_name="vectorDatabaseName",
        ))
        vector_memory_handler.agent_id = self._agent_key
        return vector_memory_handler

    def bootstrap_services_orchestrator(self):
        for key, service in self.list_services_orchestrator.items():
            service()

    def bootstrap_services_bot(self):
        for key, service in self.list_services_bot.items():
            service()

    def bootstrap_services(self):
        for key, service in self.list_services.items():
            service()

    @property
    def list_services_orchestrator(self) -> Dict[str, Callable]:
        return {
            "embedder": self.get_embedder,
        }

    @property
    def list_services_bot(self) -> Dict[str, Callable]:
        return {
            "large_language_model": self.get_large_language_model,
            "custom_auth_handler": self.get_custom_auth_handler,
            "file_manager": self.get_file_manager,
            "chunker": self.get_chunker,
            "vector_memory_handler": self.get_vector_memory_handler,
        }

    @property
    def list_services(self) -> Dict[str, Callable]:
        return self.list_services_orchestrator | self.list_services_bot
