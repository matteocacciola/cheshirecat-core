from langchain_groq import ChatGroq
from langchain_litellm import ChatLiteLLM
from langchain_openai import AzureChatOpenAI
from langchain_openai import AzureOpenAI
from langchain_community.llms import (
    HuggingFaceTextGenInference,
    HuggingFaceEndpoint,
)
from langchain_openai import ChatOpenAI, OpenAI
from langchain_cohere import ChatCohere
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_anthropic import ChatAnthropic
from langchain_mistralai import ChatMistralAI
from typing import Type
import json
from pydantic import ConfigDict

from cat.core_plugins.factories.llm.custom import LLMCustom, CustomOpenAI, CustomOllama
from cat.factory.llm import LLMSettings


class LLMCustomConfig(LLMSettings):
    url: str
    auth_key: str = "optional_auth_key"
    options: str = "{}"

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Custom LLM (Deprecated)",
            "description": "Legacy LLM adapter, you can now have it more custom in a plugin.",
            "link": "https://cheshirecat.ai/custom-large-language-model/",
        }
    )

    # instantiate Custom LLM from configuration
    @classmethod
    def get_from_config(cls, config):
        options = config["options"]
        # options are inserted as a string in the admin
        if isinstance(options, str):
            config["options"] = json.loads(options) if options != "" else {}

        return cls.pyclass()(**cls._parse_config(config))

    @classmethod
    def pyclass(cls) -> Type:
        return LLMCustom


class LLMOpenAICompatibleConfig(LLMSettings):
    url: str
    temperature: float = 0.01
    model_name: str
    api_key: str
    streaming: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI-compatible API",
            "description": "Configuration for OpenAI-compatible APIs, e.g. llama-cpp-python server, text-generation-webui, OpenRouter, TinyLLM, TogetherAI and many others.",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return CustomOpenAI


class LLMOpenAIChatConfig(LLMSettings):
    openai_api_key: str
    model_name: str = "gpt-4o-mini"
    temperature: float = 0.7
    streaming: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI ChatGPT",
            "description": "Chat model from OpenAI",
            "link": "https://platform.openai.com/docs/models/overview",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return ChatOpenAI


class LLMOpenAIConfig(LLMSettings):
    openai_api_key: str
    model_name: str = "gpt-3.5-turbo-instruct"
    temperature: float = 0.7
    streaming: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "OpenAI GPT",
            "description": "OpenAI GPT. More expensive but also more flexible than ChatGPT.",
            "link": "https://platform.openai.com/docs/models/overview",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return OpenAI


# https://learn.microsoft.com/en-gb/azure/cognitive-services/openai/reference#chat-completions
class LLMAzureChatOpenAIConfig(LLMSettings):
    openai_api_key: str
    model_name: str = "gpt-35-turbo"  # or gpt-4, use only chat models !
    azure_endpoint: str
    max_tokens: int = 2048
    openai_api_type: str = "azure"
    # Dont mix api versions https://github.com/hwchase17/langchain/issues/4775
    openai_api_version: str = "2023-05-15"
    azure_deployment: str
    streaming: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure OpenAI Chat Models",
            "description": "Chat model from Azure OpenAI",
            "link": "https://azure.microsoft.com/en-us/products/ai-services/openai-service",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return AzureChatOpenAI


# https://python.langchain.com/en/latest/modules/models/llms/integrations/azure_openai_example.html
class LLMAzureOpenAIConfig(LLMSettings):
    openai_api_key: str
    azure_endpoint: str
    max_tokens: int = 2048
    api_type: str = "azure"
    # https://learn.microsoft.com/en-us/azure/cognitive-services/openai/reference#completions
    # Current supported versions 2022-12-01, 2023-03-15-preview, 2023-05-15
    # Don't mix api versions: https://github.com/hwchase17/langchain/issues/4775
    api_version: str = "2023-05-15"
    azure_deployment: str = "gpt-35-turbo-instruct"
    model_name: str = "gpt-35-turbo-instruct"  # Use only completion models !
    streaming: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure OpenAI Completion models",
            "description": "Configuration for Cognitive Services Azure OpenAI",
            "link": "https://azure.microsoft.com/en-us/products/ai-services/openai-service",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return AzureOpenAI


class LLMCohereConfig(LLMSettings):
    cohere_api_key: str
    model: str = "command"
    temperature: float = 0.7
    streaming: bool = True

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Cohere",
            "description": "Configuration for Cohere language model",
            "link": "https://docs.cohere.com/docs/models",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return ChatCohere


# https://python.langchain.com/en/latest/modules/models/llms/integrations/huggingface_textgen_inference.html
class LLMHuggingFaceTextGenInferenceConfig(LLMSettings):
    inference_server_url: str
    max_new_tokens: int = 512
    top_k: int = 10
    top_p: float = 0.95
    typical_p: float = 0.95
    temperature: float = 0.01
    repetition_penalty: float = 1.03

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "HuggingFace TextGen Inference",
            "description": "Configuration for HuggingFace TextGen Inference",
            "link": "https://huggingface.co/text-generation-inference",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return HuggingFaceTextGenInference


# https://api.python.langchain.com/en/latest/llms/langchain_community.llms.huggingface_endpoint.HuggingFaceEndpoint.html
class LLMHuggingFaceEndpointConfig(LLMSettings):
    endpoint_url: str
    huggingfacehub_api_token: str
    task: str = "text-generation"
    max_new_tokens: int = 512
    top_k: int = None
    top_p: float = 0.95
    temperature: float = 0.8
    return_full_text: bool = False

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "HuggingFace Endpoint",
            "description": "Configuration for HuggingFace Endpoint language models",
            "link": "https://huggingface.co/inference-endpoints",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return HuggingFaceEndpoint


class LLMOllamaConfig(LLMSettings):
    base_url: str
    model: str = "llama3"
    num_ctx: int = 2048
    repeat_last_n: int = 64
    repeat_penalty: float = 1.1
    temperature: float = 0.8

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Ollama",
            "description": "Configuration for Ollama",
            "link": "https://ollama.ai/library",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return CustomOllama


class LLMGeminiChatConfig(LLMSettings):
    """
    Configuration for the Gemini large language model (LLM).

    This class inherits from the `LLMSettings` class and provides default values for the following attributes:

    * `google_api_key`: The Google API key used to access the Google Natural Language Processing (NLP) API.
    * `model`: The name of the LLM model to use. In this case, it is set to "gemini".
    * `temperature`: The temperature of the model, which controls the creativity and variety of the generated responses.
    * `top_p`: The top-p truncation value, which controls the probability of the generated words.
    * `top_k`: The top-k truncation value, which controls the number of candidate words to consider during generation.
    * `max_output_tokens`: The maximum number of tokens to generate in a single response.

    The `LLMGeminiChatConfig` class is used to create an instance of the Gemini LLM model, which can be used to generate text in natural language.
    """
    google_api_key: str
    model: str = "gemini-1.5-pro-latest"
    temperature: float = 0.1
    top_p: int = 1
    top_k: int = 1
    max_output_tokens: int = 29000

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Gemini",
            "description": "Configuration for Gemini",
            "link": "https://deepmind.google/technologies/gemini",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return ChatGoogleGenerativeAI


class LLMAnthropicChatConfig(LLMSettings):
    api_key: str
    model: str = "claude-3-5-sonnet-20241022"
    temperature: float = 0.7
    max_tokens: int = 8192
    max_retries: int = 2
    top_k: int | None = None
    top_p: float | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Anthropic",
            "description": "Configuration for Anthropic",
            "link": "https://www.anthropic.com/",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return ChatAnthropic


class LLMMistralAIChatConfig(LLMSettings):
    api_key: str
    model: str = "mistral-large-latest"
    temperature: float = 0.7
    max_tokens: int = 8192
    max_retries: int = 2
    top_p: float | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "MistralAI",
            "description": "Configuration for MistralAI",
            "link": "https://mistral.ai/",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return ChatMistralAI


class LLMGroqChatConfig(LLMSettings):
    api_key: str
    model: str = "mixtral-8x7b-32768"
    temperature: float = 0.7
    max_tokens: int | None = None
    max_retries: int = 2

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Groq",
            "description": "Configuration for Groq",
            "link": "https://groq.com/",
        },
        extra="allow",
    )

    @classmethod
    def pyclass(cls) -> Type:
        return ChatGroq


class LLMLiteLLMChatConfig(LLMSettings):
    api_key: str
    model: str = "perplexity/sonar-pro"
    temperature: float = 0.7
    max_tokens: int | None = None
    max_retries: int = 2
    top_p: int | None = None
    top_k: int | None = None

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "LiteLLM",
            "description": "Configuration for LiteLLM",
            "link": "https://www.litellm.ai/",
        },
        extra="allow",
    )

    @classmethod
    def pyclass(cls) -> Type:
        return ChatLiteLLM
