from typing import Any, Dict
from pydantic import BaseModel

from cat.db import models
from cat.db.cruds import settings as crud_settings
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.services.factory.agentic_workflow import BaseAgenticWorkflowHandler
from cat.services.factory.auth_handler import BaseAuthHandler
from cat.services.factory.embedder import Embeddings
from cat.services.factory.llm import LargeLanguageModel
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

    async def _create_service_object(self, factory: ServiceFactory):
        # if no config is saved, use default one and save to db
        # create the settings for the factory
        await crud_settings.upsert_setting_by_name(
            self._agent_key,
            models.Setting(
                name=factory.default_config_class.__name__,
                category=factory.setting_category,
                value=factory.default_config,
            ),
        )

    def _get_factory_object(self, factory_params: FactoryParams) -> ServiceFactory:
        return ServiceFactory(self._agent_key, self._plugin_manager, **factory_params.model_dump())

    async def _get_service_object(self, factory_params: FactoryParams) -> Any:
        factory = self._get_factory_object(factory_params)

        if not (selected_config := await crud_settings.get_settings_by_category(self._agent_key, factory.setting_category)):
            # if no config is saved, use the default one and save to db
            # create the settings for the factory
            await self._create_service_object(factory)

            # reload from db and return
            selected_config = crud_settings.get_settings_by_category(self._agent_key, factory.setting_category)

        return await factory.get_from_config_name(selected_config["name"])

    async def get_embedder(self) -> Embeddings:
        return await self._get_service_object(self._list_factory_params["embedder"])

    async def get_large_language_model(self) -> LargeLanguageModel:
        return await self._get_service_object(self._list_factory_params["large_language_model"])

    async def get_custom_auth_handler(self) -> BaseAuthHandler:
        return await self._get_service_object(self._list_factory_params["auth_handler"])

    async def get_file_manager(self) -> BaseFileManager:
        return await self._get_service_object(self._list_factory_params["file_manager"])

    async def get_chunker(self) -> BaseChunker:
        return await self._get_service_object(self._list_factory_params["chunker"])

    async def get_vector_memory_handler(self) -> BaseVectorDatabaseHandler:
        return await self._get_service_object(self._list_factory_params["vector_memory_handler"])

    async def get_agentic_workflow(self) -> BaseAgenticWorkflowHandler:
        agentic_workflow = await self._get_service_object(self._list_factory_params["agentic_workflow"])
        agentic_workflow.vector_memory_handler = await self.get_vector_memory_handler()
        return agentic_workflow

    async def _bootstrap_services(self, list_factory_params: Dict[str, FactoryParams]):
        for _, factory_params in list_factory_params.items():
            factory = self._get_factory_object(factory_params)
            selected_config = await crud_settings.get_settings_by_category(self._agent_key, factory.setting_category)
            if selected_config:
                continue

            # if no config is saved, use default one and save to db
            # create the settings for the factory
            await self._create_service_object(factory)

    async def bootstrap_services_orchestrator(self):
        await self._bootstrap_services(self._list_factory_params_orchestrator)

    async def bootstrap_services_bot(self):
        await self._bootstrap_services(self._list_factory_params_bot)

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
