from abc import ABC, abstractmethod
from typing import Type, List, Dict, Any, ClassVar
from pydantic import BaseModel

from cat.db.cruds import settings as crud_settings
from cat.log import log
from cat.mad_hatter import MadHatter
from cat.services.string_crypto import StringCrypto


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

    def get_config_class_from_adapter(self, cls: Type) -> Type[BaseModel] | None:
        return next(
            (config_class for config_class in self.get_allowed_classes() if config_class.pyclass() == cls),
            None
        )

    def get_schemas(self) -> Dict:
        # schemas contains metadata to let any client know which fields are required to create the class.
        schemas = {}
        for config_class in self.get_allowed_classes():
            schema = config_class.model_json_schema()
            # useful for clients in order to call the correct config endpoints
            schema[self.schema_name] = schema["title"]
            schemas[schema["title"]] = schema

        return schemas

    def _get_factory_class(self, config_name: str) -> Type[BaseModel] | None:
        return next((cls for cls in self.get_allowed_classes() if cls.__name__ == config_name), None)

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

    @property
    def default_config(self) -> Dict:
        return {k: v.default for k, v in self.default_config_class.model_fields.items()}

    @abstractmethod
    def get_allowed_classes(self) -> List[Type[BaseFactoryConfigModel]]:
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
