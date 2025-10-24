from typing import Type
from fastembed import TextEmbedding
# from langchain_cohere import CohereEmbeddings
from langchain_community.embeddings import FakeEmbeddings, FastEmbedEmbeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_mistralai import MistralAIEmbeddings
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
# from langchain_voyageai import VoyageAIEmbeddings
from pydantic import ConfigDict, Field

from cat.core_plugins.factories.embedder.custom import (
    CustomOpenAIEmbeddings,
    CustomOllamaEmbeddings,
    CustomJinaEmbedder,
)
from cat.factory.embedder import EmbedderSettings
from cat.utils import Enum


class EmbedderFakeConfig(EmbedderSettings):
    size: int = 128

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Default Embedder",
            "description": "Configuration for default embedder. It just outputs random numbers.",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return FakeEmbeddings


class EmbedderOpenAICompatibleConfig(EmbedderSettings):
    api_key: str | None = None
    model: str
    url: str

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI-compatible API embedder",
            "description": "Configuration for OpenAI-compatible API embeddings",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return CustomOpenAIEmbeddings


class EmbedderOpenAIConfig(EmbedderSettings):
    openai_api_key: str
    model: str = "text-embedding-ada-002"

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI Embedder",
            "description": "Configuration for OpenAI embeddings",
            "link": "https://platform.openai.com/docs/models/overview",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return OpenAIEmbeddings


# https://python.langchain.com/en/latest/_modules/langchain/embeddings/openai.html#OpenAIEmbeddings
class EmbedderAzureOpenAIConfig(EmbedderSettings):
    openai_api_key: str
    model: str
    azure_endpoint: str
    openai_api_type: str = "azure"
    openai_api_version: str
    deployment: str

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure OpenAI Embedder",
            "description": "Configuration for Azure OpenAI embeddings",
            "link": "https://azure.microsoft.com/en-us/products/ai-services/openai-service",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return AzureOpenAIEmbeddings


# class EmbedderCohereConfig(EmbedderSettings):
#     cohere_api_key: str
#     model: str = "embed-multilingual-v2.0"
#
#     model_config = ConfigDict(
#         json_schema_extra={
#             "humanReadableName": "Cohere Embedder",
#             "description": "Configuration for Cohere embeddings",
#             "link": "https://docs.cohere.com/docs/models",
#         }
#     )
#
#     @classmethod
#     def pyclass(cls) -> Type:
#         return CohereEmbeddings


# Enum for menu selection in the admin!
FastEmbedModels = Enum(
    "FastEmbedModels",
    {
        item["model"].replace("/", "_").replace("-", "_"): item["model"]
        for item in TextEmbedding.list_supported_models()
    },
)


class EmbedderQdrantFastEmbedConfig(EmbedderSettings):
    model_name: FastEmbedModels = Field(title="Model name", default="BAAI/bge-base-en")  # type: ignore
    # Unknown behavior for values > 512.
    max_length: int = 512
    # as suggest on fastembed documentation, "passage" is the best option for documents.
    doc_embed_type: str = "passage"
    cache_dir: str = "cat/data/models/fast_embed"

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Qdrant FastEmbed (Local)",
            "description": "Configuration for Qdrant FastEmbed",
            "link": "https://qdrant.github.io/fastembed/",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return FastEmbedEmbeddings


class EmbedderGeminiChatConfig(EmbedderSettings):
    """Configuration for Gemini Chat Embedder.

    This class contains the configuration for the Gemini Embedder.
    """
    google_api_key: str
    # Default model https://python.langchain.com/docs/integrations/text_embedding/google_generative_ai
    model: str = "models/embedding-001"

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Gemini Embedder",
            "description": "Configuration for Gemini Embedder",
            "link": "https://cloud.google.com/vertex-ai/docs/generative-ai/model-reference/text-embeddings?hl=en",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return GoogleGenerativeAIEmbeddings


class EmbedderMistralAIChatConfig(EmbedderSettings):
    """
    Configuration for Mistral AI Chat Embedder.

    This class contains the configuration for the Mistral AI Embedder.
    """
    api_key: str
    model: str = "mistral-embed"
    max_retries: int = 5
    max_concurrent_requests: int = 64

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Mistral AI Embedder",
            "description": "Configuration for MistralAI Embedder",
            "link": "https://docs.mistral.ai/capabilities/embeddings/",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return MistralAIEmbeddings


# class EmbedderVoyageAIChatConfig(EmbedderSettings):
#     """
#     Configuration for Voyage AI Chat Text Embedder.
#
#     This class contains the configuration for the Voyage AI Text Embedder.
#     """
#     api_key: str
#     model: str = "voyage-3"
#     batch_size: int
#
#     model_config = ConfigDict(
#         json_schema_extra={
#             "humanReadableName": "Voyage AI Embedder",
#             "description": "Configuration for Voyage AI Embedder",
#             "link": "https://docs.voyageai.com/docs/embeddings",
#         }
#     )
#
#     @classmethod
#     def pyclass(cls) -> Type:
#         return VoyageAIEmbeddings


class EmbedderOllamaConfig(EmbedderSettings):
    base_url: str
    model: str = "mxbai-embed-large"

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Ollama embedding models",
            "description": "Configuration for Ollama embeddings API",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return CustomOllamaEmbeddings


class EmbedderJinaConfig(EmbedderSettings):
    base_url: str
    model: str
    api_key: str
    task: str | None = "text-matching"

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Jina Embedder",
            "description": "Configuration for Jina embeddings",
            "link": "https://docs.jina.ai/api/jina/hub/index.html?highlight=embeddings#jina.hub.encoders.text.TextEncoder",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return CustomJinaEmbedder
