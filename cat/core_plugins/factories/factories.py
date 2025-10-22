from typing import List

from cat.core_plugins.factories.chunker.configs import (
    SemanticChunkerSettings,
    HTMLSemanticChunkerSettings,
    JSONChunkerSettings,
    TokenSpacyChunkerSettings,
    TokenNLTKChunkerSettings,
)
from cat.core_plugins.factories.embedder.configs import (
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
    EmbedderJinaConfig,
)
from cat.core_plugins.factories.file_manager.configs import (
    LocalFileManagerConfig,
    AWSFileManagerConfig,
    AzureFileManagerConfig,
    GoogleFileManagerConfig,
    DigitalOceanFileManagerConfig,
)
from cat.core_plugins.factories.llm.configs import (
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
from cat.factory.chunker import ChunkerSettings
from cat.factory.embedder import EmbedderSettings
from cat.factory.file_manager import FileManagerConfig
from cat.factory.llm import LLMSettings
from cat.mad_hatter.decorators import hook


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
def factory_allowed_embedders(allowed: List[EmbedderSettings], lizard) -> List:
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
        EmbedderJinaConfig,
    ]


@hook(priority=1)
def factory_allowed_file_managers(allowed: List[FileManagerConfig], cat) -> List:
    return allowed + [
        LocalFileManagerConfig,
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
