import pytest
from langchain.base_language import BaseLanguageModel
from langchain_core.embeddings import Embeddings

from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.factory.custom_chunker import BaseChunker
from cat.factory.custom_file_manager import BaseFileManager
from cat.factory.custom_vector_db import BaseVectorDatabaseHandler
from cat.mad_hatter.tweedledee import Tweedledee
from cat.factory.custom_embedder import DumbEmbedder
from cat.factory.custom_llm import LLMDefault
from cat.memory.utils import VectorMemoryCollectionTypes


def test_main_modules_loaded(cheshire_cat):
    assert isinstance(cheshire_cat.plugin_manager, Tweedledee)
    assert isinstance(cheshire_cat.large_language_model, BaseLanguageModel)
    assert isinstance(cheshire_cat.file_manager, BaseFileManager)
    assert isinstance(cheshire_cat.chunker, BaseChunker)
    assert isinstance(cheshire_cat.embedder, Embeddings)
    assert isinstance(cheshire_cat.vector_memory_handler, BaseVectorDatabaseHandler)


def test_default_llm_loaded(cheshire_cat):
    assert isinstance(cheshire_cat.large_language_model, LLMDefault)

    out = cheshire_cat.llm("Hey")
    assert "You did not configure a Language Model" in out


def test_default_embedder_loaded(lizard):
    embedder = lizard.embedder
    assert isinstance(embedder, DumbEmbedder)

    sentence = "I'm smarter than a random embedder BTW"
    sample_embed = DumbEmbedder().embed_query(sentence)
    out = embedder.embed_query(sentence)
    assert sample_embed == out


@pytest.mark.asyncio
async def test_procedures_embedded(lizard, cheshire_cat):
    embedder = lizard.embedder

    # get embedded tools
    procedures, _ = await cheshire_cat.vector_memory_handler.get_all_points(str(VectorMemoryCollectionTypes.PROCEDURAL))
    assert len(procedures) == 3

    for p in procedures:
        assert p.payload["metadata"]["source"] == "get_the_time"
        assert p.payload["metadata"]["type"] == "tool"
        trigger_type = p.payload["metadata"]["trigger_type"]
        content = p.payload["page_content"]
        assert trigger_type in ["start_example", "description"]

        if trigger_type == "start_example":
            assert content in ["what time is it", "get the time"]
        if trigger_type == "description":
            assert (
                content
                == "get_the_time: Useful to get the current time when asked. Input is always None."
            )

        # some check on the embedding
        assert isinstance(p.vector, list)
        expected_embed = embedder.embed_query(content)
        assert len(p.vector) == len(expected_embed)  # same embed


@pytest.mark.asyncio
async def test_cheshire_cat_created_with_system_key(lizard):
    with pytest.raises(ValueError) as e:
        await lizard.create_cheshire_cat(DEFAULT_SYSTEM_KEY)
