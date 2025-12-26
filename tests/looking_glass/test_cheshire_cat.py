import pytest
from langchain_core.language_models import BaseLanguageModel
from langchain_core.embeddings import Embeddings
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_community.document_loaders.parsers.pdf import PyMuPDFParser

from cat.core_plugins.multimodality.unstructured_parser import UnstructuredParser
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.looking_glass import Tweedledee
from cat.services.factory.chunker import BaseChunker
from cat.services.factory.file_manager import BaseFileManager
from cat.services.factory.vector_db import BaseVectorDatabaseHandler
from cat.services.factory.embedder import DumbEmbedder
from cat.services.factory.llm import LLMDefault


def test_main_modules_loaded(cheshire_cat):
    assert isinstance(cheshire_cat.plugin_manager, Tweedledee)
    assert isinstance(cheshire_cat.large_language_model, BaseLanguageModel)
    assert isinstance(cheshire_cat.file_manager, BaseFileManager)
    assert isinstance(cheshire_cat.chunker, BaseChunker)
    assert isinstance(cheshire_cat.embedder, Embeddings)
    assert isinstance(cheshire_cat.vector_memory_handler, BaseVectorDatabaseHandler)


def test_default_llm_loaded(cheshire_cat):
    assert isinstance(cheshire_cat.large_language_model, LLMDefault)


def test_default_embedder_loaded(lizard):
    embedder = lizard.embedder
    assert isinstance(embedder, DumbEmbedder)

    sentence = "I'm smarter than a random embedder BTW"
    sample_embed = DumbEmbedder().embed_query(sentence)
    out = embedder.embed_query(sentence)
    assert sample_embed == out


@pytest.mark.asyncio
async def test_cheshire_cat_created_with_system_key(lizard):
    with pytest.raises(ValueError):
        await lizard.create_cheshire_cat(DEFAULT_SYSTEM_KEY)


def test_file_handler_pdf(lizard, cheshire_cat):
    file_handlers = cheshire_cat.file_handlers

    assert "application/pdf" in file_handlers

    if "multimodality" in lizard.plugin_manager.plugins.keys():
        assert file_handlers["application/pdf"].__class__.__name__ == UnstructuredParser.__name__
        assert file_handlers["application/pdf"].document_loader_type == UnstructuredPDFLoader
    else:
        assert file_handlers["application/pdf"].__class__.__name__ == PyMuPDFParser.__name__
