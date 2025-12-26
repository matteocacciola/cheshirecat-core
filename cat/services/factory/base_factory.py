from abc import ABC, abstractmethod
from typing import Type, Dict, Any, ClassVar, List
from pydantic import BaseModel, model_serializer

from cat.db.cruds import settings as crud_settings
from cat.exceptions import CustomValidationException
from cat.log import log
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.services.string_crypto import StringCrypto


class UpsertSettingResponse(BaseModel):
    name: str
    value: Dict

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        """Custom serializer that will be used by FastAPI"""
        value = self.value.copy()  # Create a copy to avoid modifying the original value
        value = {
            k: "********" if isinstance(v, str) and any(suffix in k for suffix in ["_key", "_secret"]) else v
            for k, v in value.items()
        }

        return {
            "name": self.name,
            "value": value
        }


class GetSettingResponse(UpsertSettingResponse):
    scheme: Dict[str, Any] | None = None

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        """Custom serializer that will be used by FastAPI"""
        serialized = super().serialize_model()
        serialized["scheme"] = self.scheme
        return serialized

class GetSettingsResponse(BaseModel):
    settings: List[GetSettingResponse]
    selected_configuration: str | None


class BaseFactoryConfigModel(ABC, BaseModel):
    crypto: ClassVar[StringCrypto] = StringCrypto()

    @classmethod
    def _parse_config(cls, config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            k: cls.crypto.decrypt(v)
            if isinstance(v, str) and any(suffix in k for suffix in ["_key", "_secret"])
            else v
            for k, v in config.items()
        }

    @classmethod
    def get_from_config(cls, config) -> Type:
        obj = cls.pyclass()
        base_obj = cls.base_class()
        if obj is None or base_obj is None:
            raise Exception("Configuration class is invalid. It should define both pyclass and base_class methods")
        if issubclass(obj, base_obj):
            return obj(**cls._parse_config(config))
        raise Exception(f"Configuration class is invalid. It should be a valid {base_obj.__name__} class")

    @classmethod
    @abstractmethod
    def pyclass(cls) -> Type:
        pass

    @classmethod
    @abstractmethod
    def base_class(cls) -> Type:
        pass


class BaseFactory(ABC):
    def __init__(self, hook_manager: MadHatter):
        self._hook_manager = hook_manager

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

    @property
    @abstractmethod
    def factory_allowed_handler_name(self) -> str:
        pass

    @property
    @abstractmethod
    def setting_category(self) -> str:
        pass

    @property
    @abstractmethod
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        pass

    @property
    @abstractmethod
    def schema_name(self) -> str:
        pass
