from abc import ABC, abstractmethod
from typing import Type, Dict, Any, ClassVar
from pydantic import BaseModel

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
