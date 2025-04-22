from abc import ABC
from typing import Type, List
from langchain_core.embeddings import Embeddings
from langchain_mistralai import MistralAIEmbeddings
from langchain_voyageai import VoyageAIEmbeddings
from pydantic import ConfigDict, Field
from langchain_cohere import CohereEmbeddings
from langchain_community.embeddings import FakeEmbeddings, FastEmbedEmbeddings
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from fastembed import TextEmbedding

from cat.factory.base_factory import BaseFactory, BaseFactoryConfigModel
from cat.factory.custom_embedder import DumbEmbedder, CustomOpenAIEmbeddings, CustomOllamaEmbeddings
from cat.utils import Enum


class EmbedderSettings(BaseFactoryConfigModel, ABC):
    _is_multimodal: bool = False

    # class instantiating the embedder
    _pyclass: Type[Embeddings] = None

    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type:
        return Embeddings

    @classmethod
    def is_multimodal(cls) -> bool:
        return cls._is_multimodal.default


class EmbedderMultimodalSettings(EmbedderSettings, ABC):
    _is_multimodal: bool = True


class EmbedderFakeConfig(EmbedderSettings):
    size: int = 128

    _pyclass: Type = FakeEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Default Embedder",
            "description": "Configuration for default embedder. It just outputs random numbers.",
            "link": "",
        }
    )


class EmbedderDumbConfig(EmbedderSettings):
    _pyclass: Type = DumbEmbedder

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Dumb Embedder",
            "description": "Configuration for default embedder. It encodes the pairs of characters",
            "link": "",
        }
    )


class EmbedderOpenAICompatibleConfig(EmbedderSettings):
    url: str

    _pyclass: Type = CustomOpenAIEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI-compatible API embedder",
            "description": "Configuration for OpenAI-compatible API embeddings",
            "link": "",
        }
    )


class EmbedderOpenAIConfig(EmbedderSettings):
    openai_api_key: str
    model: str = "text-embedding-ada-002"

    _pyclass: Type = OpenAIEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI Embedder",
            "description": "Configuration for OpenAI embeddings",
            "link": "https://platform.openai.com/docs/models/overview",
        }
    )


# https://python.langchain.com/en/latest/_modules/langchain/embeddings/openai.html#OpenAIEmbeddings
class EmbedderAzureOpenAIConfig(EmbedderSettings):
    openai_api_key: str
    model: str
    azure_endpoint: str
    openai_api_type: str = "azure"
    openai_api_version: str
    deployment: str

    _pyclass: Type = AzureOpenAIEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure OpenAI Embedder",
            "description": "Configuration for Azure OpenAI embeddings",
            "link": "https://azure.microsoft.com/en-us/products/ai-services/openai-service",
        }
    )


class EmbedderCohereConfig(EmbedderSettings):
    cohere_api_key: str
    model: str = "embed-multilingual-v2.0"

    _pyclass: Type = CohereEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Cohere Embedder",
            "description": "Configuration for Cohere embeddings",
            "link": "https://docs.cohere.com/docs/models",
        }
    )


# Enum for menu selection in the admin!
FastEmbedModels = Enum(
    "FastEmbedModels",
    {
        item["model"].replace("/", "_").replace("-", "_"): item["model"]
        for item in TextEmbedding.list_supported_models()
    },
)


class EmbedderQdrantFastEmbedConfig(EmbedderSettings):
    model_name: FastEmbedModels = Field(title="Model name", default="BAAI/bge-base-en")
    # Unknown behavior for values > 512.
    max_length: int = 512
    # as suggest on fastembed documentation, "passage" is the best option for documents.
    doc_embed_type: str = "passage"
    cache_dir: str = "cat/data/models/fast_embed"

    _pyclass: Type = FastEmbedEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Qdrant FastEmbed (Local)",
            "description": "Configuration for Qdrant FastEmbed",
            "link": "https://qdrant.github.io/fastembed/",
        }
    )


class EmbedderGeminiChatConfig(EmbedderSettings):
    """Configuration for Gemini Chat Embedder.

    This class contains the configuration for the Gemini Embedder.
    """

    google_api_key: str
    # Default model https://python.langchain.com/docs/integrations/text_embedding/google_generative_ai
    model: str = "models/embedding-001"

    _pyclass: Type = GoogleGenerativeAIEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Gemini Embedder",
            "description": "Configuration for Gemini Embedder",
            "link": "https://cloud.google.com/vertex-ai/docs/generative-ai/model-reference/text-embeddings?hl=en",
        }
    )


class EmbedderMistralAIChatConfig(EmbedderSettings):
    """
    Configuration for Mistral AI Chat Embedder.

    This class contains the configuration for the Mistral AI Embedder.
    """

    api_key: str
    model: str = "mistral-embed"
    max_retries: int = 5
    max_concurrent_requests: int = 64

    _pyclass: Type = MistralAIEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Mistral AI Embedder",
            "description": "Configuration for MistralAI Embedder",
            "link": "https://docs.mistral.ai/capabilities/embeddings/",
        }
    )


class EmbedderVoyageAIChatConfig(EmbedderSettings):
    """
    Configuration for Voyage AI Chat Text Embedder.

    This class contains the configuration for the Voyage AI Text Embedder.
    """

    api_key: str
    model: str = "voyage-3"
    batch_size: int

    _pyclass: Type = VoyageAIEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Voyage AI Embedder",
            "description": "Configuration for Voyage AI Embedder",
            "link": "https://docs.voyageai.com/docs/embeddings",
        }
    )


class EmbedderOllamaConfig(EmbedderSettings):
    base_url: str
    model: str = "mxbai-embed-large"
    _pyclass: Type = CustomOllamaEmbeddings

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Ollama embedding models",
            "description": "Configuration for Ollama embeddings API",
            "link": "",
            "model": "mxbai-embed-large",
        }
    )


class EmbedderFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[EmbedderSettings]]:
        list_embedder_default = [
            EmbedderQdrantFastEmbedConfig,
            EmbedderOpenAIConfig,
            EmbedderAzureOpenAIConfig,
            EmbedderGeminiChatConfig,
            EmbedderOpenAICompatibleConfig,
            EmbedderCohereConfig,
            EmbedderDumbConfig,
            EmbedderFakeConfig,
            EmbedderMistralAIChatConfig,
            EmbedderVoyageAIChatConfig,
            EmbedderOllamaConfig,
        ]

        list_embedder = self._hook_manager.execute_hook(
            "factory_allowed_embedders", list_embedder_default, cat=None
        )
        return list_embedder

    @property
    def setting_name(self) -> str:
        return "embedder_selected"

    @property
    def setting_category(self) -> str:
        return "embedder"

    @property
    def setting_factory_category(self) -> str:
        return "embedder_factory"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return EmbedderDumbConfig

    @property
    def schema_name(self) -> str:
        return "languageEmbedderName"
