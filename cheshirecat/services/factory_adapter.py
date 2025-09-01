from typing import Dict, Final, Any
from pydantic import BaseModel

from cheshirecat.db import models
from cheshirecat.db.cruds import settings as crud_settings
from cheshirecat.factory.base_factory import BaseFactory
from cheshirecat.services.string_crypto import StringCrypto


class UpdaterFactory(BaseModel):
    old_setting: Dict | None = None
    old_factory: Dict | None = None
    new_setting: Dict | None = None


class FactoryAdapter:
    def __init__(self, factory: BaseFactory):
        self._factory = factory
        self.crypto: Final = StringCrypto()

    def _encrypt_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        return {
            k: self.crypto.encrypt(v)
            if isinstance(v, str) and any(suffix in k for suffix in ["_key", "_secret"])
            else v
            for k, v in config.items()
        }

    def get_factory_config_by_settings(self, key_id: str) -> Dict:
        selected_config = crud_settings.get_setting_by_name(key_id, self._factory.setting_name)
        if selected_config:
            return selected_config

        default_factory_name = self._factory.default_config_class.__name__

        # if no config is saved, use default one and save to db
        # create the settings for the factory
        crud_settings.upsert_setting_by_name(
            key_id,
            models.Setting(
                name=default_factory_name,
                category=self._factory.setting_factory_category,
                value=self._factory.default_config,
            ),
        )
        # create the settings to set the class of the factory
        crud_settings.upsert_setting_by_name(key_id, models.Setting(
            name=self._factory.setting_name,
            category=self._factory.setting_category,
            value={"name": default_factory_name},
        ))

        # reload from db and return
        return crud_settings.get_setting_by_name(key_id, self._factory.setting_name)

    def upsert_factory_config_by_settings(
        self, key_id: str, new_factory_name: str, new_factory_settings: Dict,
    ) -> UpdaterFactory:
        current_setting = crud_settings.get_setting_by_name(key_id, self._factory.setting_name)
        current_factory = (
            crud_settings.get_setting_by_name(key_id, current_setting["value"]["name"]) if current_setting else None
        )

        # upsert the settings for the factory
        final_setting = crud_settings.upsert_setting_by_category(key_id, models.Setting(
            name=new_factory_name,
            category=self._factory.setting_factory_category,
            value=self._encrypt_config(new_factory_settings),
        ))

        # upsert the setting for the class of the factory
        crud_settings.upsert_setting_by_name(key_id, models.Setting(
            name=self._factory.setting_name, category=self._factory.setting_category, value={"name": new_factory_name}),
        )

        return UpdaterFactory(old_setting=current_setting, old_factory=current_factory, new_setting=final_setting)

    def rollback_factory_config(self, key_id: str) -> None:
        crud_settings.delete_settings_by_category(key_id, self._factory.setting_category)
        crud_settings.delete_settings_by_category(key_id, self._factory.setting_factory_category)