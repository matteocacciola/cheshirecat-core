from typing import Type, Dict, Any, List, Literal

from cat.db.cruds import settings as crud_settings
from cat.exceptions import CustomValidationException
from cat.log import log
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse
from cat.services.factory.agentic_workflow import CoreAgenticWorkflowConfig
from cat.services.factory.auth_handler import CoreAuthConfig
from cat.services.factory.chunker import RecursiveTextChunkerSettings
from cat.services.factory.embedder import EmbedderDumbConfig
from cat.services.factory.file_manager import DummyFileManagerConfig
from cat.services.factory.llm import LLMDefaultConfig
from cat.services.factory.models import BaseFactoryConfigModel
from cat.services.factory.vector_db import QdrantConfig


class ServiceFactory:
    def __init__(
        self,
        hook_manager: MadHatter,
        factory_allowed_handler_name: str,
        setting_category: Literal[
            "auth_handler", "chunker", "embedder", "file_manager", "llm", "vector_database", "agentic_workflow"
        ],
        schema_name: str,
    ):
        self._hook_manager = hook_manager
        self.factory_allowed_handler_name = factory_allowed_handler_name
        self.setting_category = setting_category
        self.default_config_class = self.default_config_classes[setting_category]
        self.schema_name = schema_name

    @property
    def default_config_classes(self) -> Dict[str, Type[BaseFactoryConfigModel]]:
        return {
            "agentic_workflow": CoreAgenticWorkflowConfig,
            "auth_handler": CoreAuthConfig,
            "chunker": RecursiveTextChunkerSettings,
            "embedder": EmbedderDumbConfig,
            "file_manager": DummyFileManagerConfig,
            "llm": LLMDefaultConfig,
            "vector_database": QdrantConfig,
        }

    def get_schemas(self) -> Dict:
        # schemas contains metadata to let any client know which fields are required to create the class.
        schemas = {}
        for config_class in self.get_allowed_classes():
            schema = config_class.model_json_schema()
            # useful for clients in order to call the correct config endpoints
            schema[self.schema_name] = schema["title"]
            schemas[schema["title"]] = schema

        return schemas

    def get_from_config_name(self, agent_id: str, config_name: str) -> Any:
        # get plugin file manager factory class
        factory_class = next((cls for cls in self.get_allowed_classes() if cls.__name__ == config_name), None)
        if not factory_class:
            log.warning(
                f"Class {config_name} not found in the list of allowed classes for setting '{self.setting_category}'"
            )
            return self.default_config_class.get_from_config(self.default_config)

        # obtain configuration and instantiate the finalized object by the factory
        selected_config = crud_settings.get_setting_by_name(agent_id, config_name)
        try:
            return factory_class.get_from_config(selected_config["value"])
        except:
            return self.default_config_class.get_from_config(self.default_config)

    def get_allowed_classes(self) -> List[Type[BaseFactoryConfigModel]]:
        return self._hook_manager.execute_hook(
            self.factory_allowed_handler_name, [self.default_config_class], caller=None
        )

    def upsert_service(self, agent_key: str, service_name: str, payload: Dict) -> Dict:
        from cat.services.service_updater import ServiceUpdater

        schemas = self.get_schemas()

        allowed_configurations = list(schemas.keys())
        if service_name not in allowed_configurations:
            raise CustomValidationException(
                f"{service_name} not supported. Must be one of {allowed_configurations}")

        updater_service = ServiceUpdater(agent_key, self)
        result = updater_service.replace_service(service_name, payload)

        return result

    def get_factory_settings(self, agent_key: str) -> GetSettingsResponse:
        saved_settings = crud_settings.get_settings_by_category(agent_key, self.setting_category)

        settings = [GetSettingResponse(
            name=class_name,
            value=saved_settings["value"] if class_name == saved_settings["name"] else {},
            scheme=scheme
        ) for class_name, scheme in self.get_schemas().items()]

        return GetSettingsResponse(settings=settings, selected_configuration=saved_settings["name"])

    def get_factory_setting(self, agent_key: str, configuration_name: str) -> GetSettingResponse:
        schemas = self.get_schemas()

        allowed_configurations = list(schemas.keys())
        if configuration_name not in allowed_configurations:
            raise CustomValidationException(
                f"{configuration_name} not supported. Must be one of {allowed_configurations}")

        setting = crud_settings.get_setting_by_name(agent_key, configuration_name)
        setting = {} if setting is None else setting["value"]

        scheme = schemas[configuration_name]

        return GetSettingResponse(name=configuration_name, value=setting, scheme=scheme)

    @property
    def default_config(self) -> Dict:
        return {k: v.default for k, v in self.default_config_class.model_fields.items()}
