from typing import List

from cheshirecat.core_plugins.factories.chunker.configs import (
    SemanticChunkerSettings,
    HTMLSemanticChunkerSettings,
    JSONChunkerSettings,
    TokenSpacyChunkerSettings,
    TokenNLTKChunkerSettings,
)
from cheshirecat.core_plugins.factories.embedder.configs import (
    EmbedderQdrantFastEmbedConfig,
    EmbedderOpenAIConfig,
    EmbedderAzureOpenAIConfig,
    EmbedderGeminiChatConfig,
    EmbedderOpenAICompatibleConfig,
    EmbedderCohereConfig,
    EmbedderFakeConfig,
    EmbedderMistralAIChatConfig,
    EmbedderVoyageAIChatConfig,
    EmbedderOllamaConfig,
)
from cheshirecat.core_plugins.factories.file_manager.configs import (
    AWSFileManagerConfig,
    AzureFileManagerConfig,
    GoogleFileManagerConfig,
    DigitalOceanFileManagerConfig,
)
from cheshirecat.core_plugins.factories.llm.configs import (
    LLMOpenAIChatConfig,
    LLMOpenAIConfig,
    LLMOpenAICompatibleConfig,
    LLMOllamaConfig,
    LLMGeminiChatConfig,
    LLMCohereConfig,
    LLMAzureOpenAIConfig,
    LLMAzureChatOpenAIConfig,
    LLMHuggingFaceEndpointConfig,
    LLMHuggingFaceTextGenInferenceConfig,
    LLMCustomConfig,
    LLMAnthropicChatConfig,
    LLMMistralAIChatConfig,
    LLMGroqChatConfig,
    LLMLiteLLMChatConfig,
)
from cheshirecat.factory.chunker import ChunkerSettings
from cheshirecat.factory.llm import LLMSettings
from cheshirecat.factory.embedder import EmbedderSettings
from cheshirecat.factory.file_manager import FileManagerConfig
from cheshirecat.mad_hatter.decorators import hook


@hook(priority=1)
def factory_allowed_llms(allowed: List[LLMSettings], cat) -> List:
    return allowed + [
        LLMOpenAIChatConfig,
        LLMOpenAIConfig,
        LLMOpenAICompatibleConfig,
        LLMOllamaConfig,
        LLMGeminiChatConfig,
        LLMCohereConfig,
        LLMAzureOpenAIConfig,
        LLMAzureChatOpenAIConfig,
        LLMHuggingFaceEndpointConfig,
        LLMHuggingFaceTextGenInferenceConfig,
        LLMCustomConfig,
        LLMAnthropicChatConfig,
        LLMMistralAIChatConfig,
        LLMGroqChatConfig,
        LLMLiteLLMChatConfig,
    ]


@hook(priority=1)
def factory_allowed_embedders(allowed: List[EmbedderSettings], cat) -> List:
    return allowed + [
        EmbedderQdrantFastEmbedConfig,
        EmbedderOpenAIConfig,
        EmbedderAzureOpenAIConfig,
        EmbedderGeminiChatConfig,
        EmbedderOpenAICompatibleConfig,
        EmbedderCohereConfig,
        EmbedderFakeConfig,
        EmbedderMistralAIChatConfig,
        EmbedderVoyageAIChatConfig,
        EmbedderOllamaConfig,
    ]


@hook(priority=1)
def factory_allowed_file_managers(allowed: List[FileManagerConfig], cat) -> List:
    return allowed + [
        AWSFileManagerConfig,
        AzureFileManagerConfig,
        GoogleFileManagerConfig,
        DigitalOceanFileManagerConfig,
    ]

@hook(priority=1)
def factory_allowed_chunkers(allowed: List[ChunkerSettings], cat) -> List:
    return allowed + [
        SemanticChunkerSettings,
        HTMLSemanticChunkerSettings,
        JSONChunkerSettings,
        TokenSpacyChunkerSettings,
        TokenNLTKChunkerSettings,
    ]
