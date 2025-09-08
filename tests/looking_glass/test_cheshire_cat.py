import pytest
from langchain.base_language import BaseLanguageModel
from langchain_core.embeddings import Embeddings

from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.factory.chunker import BaseChunker
from cat.factory.file_manager import BaseFileManager
from cat.factory.vector_db import BaseVectorDatabaseHandler
from cat.mad_hatter import Tweedledee
from cat.factory.embedder import DumbEmbedder
from cat.factory.llm import LLMDefault


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
