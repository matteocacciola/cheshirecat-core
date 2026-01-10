from typing import Any, Dict
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel
from pydantic import BaseModel

from cat.db import models
from cat.db.cruds import settings as crud_settings
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.services.factory.agentic_workflow import BaseAgenticWorkflowHandler
from cat.services.factory.auth_handler import BaseAuthHandler
from cat.services.service_factory import ServiceFactory
from cat.services.factory.chunker import BaseChunker
from cat.services.factory.file_manager import BaseFileManager
from cat.services.factory.vector_db import BaseVectorDatabaseHandler


class FactoryParams(BaseModel):
    factory_allowed_handler_name: str
    setting_category: str
    schema_name: str


class ServiceProvider:
    def __init__(self, agent_key: str, plugin_manager: MadHatter):
        self._agent_key = agent_key
        self._plugin_manager = plugin_manager

    def _create_service_object(self, factory: ServiceFactory):
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

    def _get_factory_object(self, factory_params: FactoryParams) -> ServiceFactory:
        return ServiceFactory(self._plugin_manager, **factory_params.model_dump())

    def _get_service_object(self, factory_params: FactoryParams) -> Any:
        factory = self._get_factory_object(factory_params)

        if not (selected_config := crud_settings.get_settings_by_category(self._agent_key, factory.setting_category)):
            # if no config is saved, use default one and save to db
            # create the settings for the factory
            self._create_service_object(factory)

            # reload from db and return
            selected_config = crud_settings.get_settings_by_category(self._agent_key, factory.setting_category)

        service = factory.get_from_config_name(self._agent_key, selected_config["name"])
        if hasattr(service, "agent_id"):
            service.agent_id = self._agent_key
        return service

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
        return self._get_service_object(self._list_factory_params["embedder"])

    def get_large_language_model(self) -> BaseLanguageModel:
        return self._get_service_object(self._list_factory_params["large_language_model"])

    def get_custom_auth_handler(self) -> BaseAuthHandler:
        return self._get_service_object(self._list_factory_params["auth_handler"])

    def get_file_manager(self) -> BaseFileManager:
        return self._get_service_object(self._list_factory_params["file_manager"])

    def get_chunker(self) -> BaseChunker:
        return self._get_service_object(self._list_factory_params["chunker"])

    def get_vector_memory_handler(self) -> BaseVectorDatabaseHandler:
        return self._get_service_object(self._list_factory_params["vector_memory_handler"])

    def get_agentic_workflow(self) -> BaseAgenticWorkflowHandler:
        return self._get_service_object(self._list_factory_params["agentic_workflow"])

    def _bootstrap_services(self, list_factory_params: Dict[str, FactoryParams]):
        for _, factory_params in list_factory_params.items():
            factory = self._get_factory_object(factory_params)
            selected_config = crud_settings.get_settings_by_category(self._agent_key, factory.setting_category)
            if selected_config:
                continue

            # if no config is saved, use default one and save to db
            # create the settings for the factory
            self._create_service_object(factory)

    def bootstrap_services_orchestrator(self):
        self._bootstrap_services(self._list_factory_params_orchestrator)

    def bootstrap_services_bot(self):
        self._bootstrap_services(self._list_factory_params_bot)

    @property
    def _list_factory_params_orchestrator(self) -> Dict[str, FactoryParams]:
        return {
            "embedder": FactoryParams(
                factory_allowed_handler_name="factory_allowed_embedders",
                setting_category="embedder",
                schema_name="languageEmbedderName",
            ),
        }

    @property
    def _list_factory_params_bot(self) -> Dict[str, FactoryParams]:
        return {
            "agentic_workflow": FactoryParams(
                factory_allowed_handler_name="factory_allowed_agentic_workflows",
                setting_category="agentic_workflow",
                schema_name="agenticWorkflowName",
            ),
            "large_language_model": FactoryParams(
                factory_allowed_handler_name="factory_allowed_llms",
                setting_category="llm",
                schema_name="languageModelName",
            ),
            "auth_handler": FactoryParams(
                factory_allowed_handler_name="factory_allowed_auth_handlers",
                setting_category="auth_handler",
                schema_name="authorizatorName",
            ),
            "file_manager": FactoryParams(
                factory_allowed_handler_name="factory_allowed_file_managers",
                setting_category="file_manager",
                schema_name="fileManagerName",
            ),
            "chunker": FactoryParams(
                factory_allowed_handler_name="factory_allowed_chunkers",
                setting_category="chunker",
                schema_name="chunkerName",
            ),
            "vector_memory_handler": FactoryParams(
                factory_allowed_handler_name="factory_allowed_vector_databases",
                setting_category="vector_database",
                schema_name="vectorDatabaseName",
            ),
        }

    @property
    def _list_factory_params(self) -> Dict[str, FactoryParams]:
        return self._list_factory_params_orchestrator | self._list_factory_params_bot
