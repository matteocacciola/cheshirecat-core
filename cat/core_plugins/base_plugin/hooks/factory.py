from typing import List

from cat import (
    AuthHandlerConfig,
    ChunkerSettings,
    EmbedderSettings,
    FileManagerConfig,
    LLMSettings,
    VectorDatabaseSettings,
    hook,
)


@hook(priority=0)
def factory_allowed_llms(allowed: List[LLMSettings], cat) -> List:
    """
    Hook to extend support of llms.

    Args:
        allowed: List of LLMSettings classes
        cat: CheshireCat instance

    Returns:
        list of allowed LLMSettings classes for the allowed language models
    """
    return allowed


@hook(priority=0)
def factory_allowed_embedders(allowed: List[EmbedderSettings], lizard) -> List:
    """Hook to extend list of supported embedders.

    Args:
        allowed: List of EmbedderSettings classes
        lizard: BillTheLizard instance

    Returns:
        list of allowed EmbedderSettings classes for the allowed embedders
    """
    return allowed


@hook(priority=0)
def factory_allowed_auth_handlers(allowed: List[AuthHandlerConfig], cat) -> List:
    """Hook to extend list of supported auth_handlers.

    Args:
        allowed: List of AuthHandlerConfig classes
        cat: Cheshire Cat instance

    Returns:
        supported: List of AuthHandlerConfig classes for the allowed auth_handlers
    """
    return allowed


@hook(priority=0)
def factory_allowed_file_managers(allowed: List[FileManagerConfig], cat) -> List:
    """Hook to extend list of supported file managers.

    Args:
        allowed: List of FileManagerConfig classes
        cat: Cheshire Cat instance

    Returns:
        supported: List of FileManagerConfig classes for the allowed file managers
    """
    return allowed


@hook(priority=0)
def factory_allowed_chunkers(allowed: List[ChunkerSettings], cat) -> List:
    """Hook to extend list of supported chunkers.

    Args:
        allowed: List of ChunkerSettings classes
        cat: Cheshire Cat instance

    Returns:
        supported: List of ChunkerSettings classes for the allowed chunkers
    """
    return allowed


@hook(priority=0)
def factory_allowed_vector_databases(allowed: List[VectorDatabaseSettings], cat) -> List:
    """Hook to extend list of supported vector databases.

    Args:
        allowed: List of VectorDatabaseSettings classes
        cat: Cheshire Cat instance

    Returns:
        supported: List of VectorDatabaseSettings classes for the allowed vector databases
    """
    return allowed
