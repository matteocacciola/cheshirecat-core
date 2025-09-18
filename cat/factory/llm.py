from abc import ABC
from typing import Type, List, Any
from langchain_core.callbacks import CallbackManagerForLLMRun, AsyncCallbackManagerForLLMRun
from langchain_core.language_models import BaseLanguageModel, LLM
from pydantic import ConfigDict

from cat.factory.base_factory import BaseFactory, BaseFactoryConfigModel
from cat.utils import default_llm_answer_prompt


class LLMDefault(LLM):
    @property
    def _llm_type(self):
        return ""

    def _call(
        self,
        prompt: str,
        stop: List[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        return default_llm_answer_prompt()

    async def _acall(
        self,
        prompt: str,
        stop: List[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> str:
        return default_llm_answer_prompt()


class LLMSettings(BaseFactoryConfigModel, ABC):
    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type:
        return BaseLanguageModel


class LLMDefaultConfig(LLMSettings):
    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Default Language Model",
            "description": "A dumb LLM just telling that the Cat is not configured. "
            "There will be a nice LLM here once consumer hardware allows it.",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return LLMDefault


class LLMFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[LLMSettings]]:
        list_llms = self._hook_manager.execute_hook("factory_allowed_llms", [LLMDefaultConfig], cat=None)
        return list_llms

    @property
    def setting_category(self) -> str:
        return "llm"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return LLMDefaultConfig

    @property
    def schema_name(self) -> str:
        return "languageModelName"
