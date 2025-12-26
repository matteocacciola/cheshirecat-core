from typing import List

from cat import hook
from cat.core_plugins.factories.chunker.configs import (
    SemanticChunkerSettings,
    HTMLSemanticChunkerSettings,
    JSONChunkerSettings,
    TokenSpacyChunkerSettings,
    TokenNLTKChunkerSettings,
    HierarchicalChunkerSettings,
    MathAwareHierarchicalChunkerSettings,
)
from cat.core_plugins.factories.embedder.configs import (
    EmbedderQdrantFastEmbedConfig,
    EmbedderOpenAIConfig,
    EmbedderAzureOpenAIConfig,
    EmbedderGeminiChatConfig,
    EmbedderOpenAICompatibleConfig,
    # EmbedderCohereConfig,
    EmbedderFakeConfig,
    EmbedderMistralAIChatConfig,
    # EmbedderVoyageAIChatConfig,
    EmbedderOllamaConfig,
    EmbedderJinaConfig,
    Qwen3LocalEmbeddingsConfig,
    Qwen3OllamaEmbeddingsConfig,
    Qwen3DeepInfraEmbeddingsConfig,
    Qwen3TEIEmbeddingsConfig,
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
    # LLMCohereConfig,
    LLMAzureOpenAIConfig,
    LLMAzureChatOpenAIConfig,
    LLMHuggingFaceEndpointConfig,
    LLMHuggingFaceTextGenInferenceConfig,
    LLMAnthropicChatConfig,
    LLMMistralAIChatConfig,
    LLMGroqChatConfig,
    # LLMLiteLLMChatConfig,
)
from cat.services.factory.chunker import ChunkerSettings
from cat.services.factory.embedder import EmbedderSettings
from cat.services.factory.file_manager import FileManagerConfig
from cat.services.factory.llm import LLMSettings


@hook(priority=1)
def factory_allowed_llms(allowed: List[LLMSettings], cat) -> List:
    return allowed + [
        LLMOpenAIChatConfig,
        LLMOpenAIConfig,
        LLMOpenAICompatibleConfig,
        LLMOllamaConfig,
        LLMGeminiChatConfig,
        # LLMCohereConfig,
        LLMAzureOpenAIConfig,
        LLMAzureChatOpenAIConfig,
        LLMHuggingFaceEndpointConfig,
        LLMHuggingFaceTextGenInferenceConfig,
        LLMAnthropicChatConfig,
        LLMMistralAIChatConfig,
        LLMGroqChatConfig,
        # LLMLiteLLMChatConfig,
    ]


@hook(priority=1)
def factory_allowed_embedders(allowed: List[EmbedderSettings], lizard) -> List:
    return allowed + [
        EmbedderQdrantFastEmbedConfig,
        EmbedderOpenAIConfig,
        EmbedderAzureOpenAIConfig,
        EmbedderGeminiChatConfig,
        EmbedderOpenAICompatibleConfig,
        # EmbedderCohereConfig,
        EmbedderFakeConfig,
        EmbedderMistralAIChatConfig,
        # EmbedderVoyageAIChatConfig,
        EmbedderOllamaConfig,
        EmbedderJinaConfig,
        Qwen3LocalEmbeddingsConfig,
        Qwen3OllamaEmbeddingsConfig,
        Qwen3DeepInfraEmbeddingsConfig,
        Qwen3TEIEmbeddingsConfig,
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
        HierarchicalChunkerSettings,
        MathAwareHierarchicalChunkerSettings,
    ]
