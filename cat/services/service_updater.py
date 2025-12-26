from typing import Dict

from cat.db import models
from cat.db.cruds import settings as crud_settings
from cat.log import log
from cat.services.factory.base_factory import BaseFactory
from cat.services.string_crypto import StringCrypto
from cat.utils import UpdaterFactory


class ServiceUpdater:
    def __init__(self, agent_key: str, factory: BaseFactory):
        self._agent_key = agent_key
        self._factory = factory

    def _update_factory_object(self, settings_name: str, settings: Dict) -> UpdaterFactory:
        """
        Update the settings of the factory object. This method upserts the settings in the database and returns
        an UpdaterFactory object containing the old and new settings.

        Args:
            settings_name: name of the settings
            settings: settings to update

        Returns:
            UpdaterFactory: object containing old and new settings
        """
        current_setting = crud_settings.get_settings_by_category(self._agent_key, self._factory.setting_category)

        # upsert the settings for the factory
        crypto = StringCrypto()
        final_setting = crud_settings.upsert_setting_by_category(self._agent_key, models.Setting(
            name=settings_name,
            category=self._factory.setting_category,
            value={
                k: crypto.encrypt(v)
                if isinstance(v, str) and any(suffix in k for suffix in ["_key", "_secret"])
                else v
                for k, v in settings.items()
            },
        ))

        return UpdaterFactory(old_setting=current_setting, new_setting=final_setting)

    def replace_service(self, model_provider_name: str, settings: Dict) -> Dict:
        """
        Replace the current service with a new one based on the provided name and settings.

        Args:
            model_provider_name: name of the new Service
            settings: settings of the new Service

        Returns:
            The dictionary resuming the new name and settings of the LLM
        """
        updater = None
        try:
            updater = self._update_factory_object(model_provider_name, settings)

            return {"name": model_provider_name, "value": updater.new_setting["value"]}  # type: ignore
        except Exception as e:
            log.error(f"Agent id: {self._agent_key}. Error while loading the new Service: {e}")

            # something went wrong: rollback
            if updater is not None and updater.old_setting is not None:
                self.replace_service(updater.old_setting["name"], updater.old_setting["value"])  # type: ignore

            raise e
