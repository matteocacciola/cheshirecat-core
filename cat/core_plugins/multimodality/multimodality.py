from typing import List, Dict
import nltk
from langchain_community.document_loaders import (
    UnstructuredWordDocumentLoader,
    UnstructuredPowerPointLoader,
    UnstructuredExcelLoader,
    UnstructuredImageLoader,
    UnstructuredPDFLoader,
)

from cat import hook, EmbedderSettings, BillTheLizard
from cat.core_plugins.multimodality.embedder import EmbedderJinaMultimodalConfig, JinaCLIPEmbeddingsConfig
from cat.core_plugins.multimodality.unstructured_parser import UnstructuredParser
from cat.services.service_factory import ServiceFactory

nltk.download("punkt")
nltk.download("averaged_perceptron_tagger")


@hook(priority=0)
def factory_allowed_embedders(allowed: List[EmbedderSettings], lizard) -> List:
    return allowed + [
        EmbedderJinaMultimodalConfig,
        JinaCLIPEmbeddingsConfig,
    ]


@hook(priority=0)
def rabbithole_instantiates_parsers(file_handlers: Dict, cat) -> Dict:
    """Hook the available parsers for ingesting files in the declarative memory.

    Allows replacing or extending existing supported mime types and related parsers to customize the file ingestion.

    Args:
        file_handlers: Dict
            Keys are the supported mime types and values are the related parsers.
        cat: CheshireCat
            Cheshire Cat instance.

    Returns:
        file_handlers: Dict
            Edited dictionary of supported mime types and related parsers.
    """
    lizard = BillTheLizard()
    embedder_config: EmbedderSettings | None = ServiceFactory(
        agent_key=lizard.agent_key,
        hook_manager=lizard.plugin_manager,
        factory_allowed_handler_name="factory_allowed_embedders",
        setting_category="embedder",
        schema_name="languageEmbedderName",
    ).get_config_class_from_adapter(lizard.embedder)

    if embedder_config and embedder_config.is_multimodal():
        file_handlers.update({
            "application/msword": UnstructuredParser(UnstructuredWordDocumentLoader),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": UnstructuredParser(
                UnstructuredWordDocumentLoader
            ),
            "application/vnd.ms-powerpoint": UnstructuredParser(UnstructuredPowerPointLoader),
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": UnstructuredParser(
                UnstructuredPowerPointLoader
            ),
            "application/pdf": UnstructuredParser(UnstructuredPDFLoader),
            "application/vnd.ms-excel": UnstructuredParser(UnstructuredExcelLoader),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": UnstructuredParser(
                UnstructuredExcelLoader),
            "image/png": UnstructuredParser(UnstructuredImageLoader),
            "image/jpeg": UnstructuredParser(UnstructuredImageLoader),
            "image/jpg": UnstructuredParser(UnstructuredImageLoader),
            "image/gif": UnstructuredParser(UnstructuredImageLoader),
            "image/bmp": UnstructuredParser(UnstructuredImageLoader),
            "image/tiff": UnstructuredParser(UnstructuredImageLoader),
            "image/webp": UnstructuredParser(UnstructuredImageLoader),
        })

    return file_handlers
