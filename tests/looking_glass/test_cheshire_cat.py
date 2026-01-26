import pytest
from langchain_core.language_models import BaseLanguageModel
from langchain_core.embeddings import Embeddings
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_community.document_loaders.parsers.pdf import PyMuPDFParser

from cat.core_plugins.multimodality.unstructured_parser import UnstructuredParser
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.looking_glass import MadHatter
from cat.services.factory.chunker import BaseChunker
from cat.services.factory.file_manager import BaseFileManager
from cat.services.factory.vector_db import BaseVectorDatabaseHandler
from cat.services.factory.embedder import DumbEmbedder
from cat.services.factory.llm import LLMDefault
from tests.utils import create_mock_plugin_zip


def test_main_modules_loaded(cheshire_cat):
    assert isinstance(cheshire_cat.plugin_manager, MadHatter)
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


def test_file_handler_pdf(lizard, cheshire_cat, secure_client, secure_client_headers):
    file_handlers = cheshire_cat.file_handlers
    assert "application/pdf" in file_handlers
    assert file_handlers["application/pdf"].__class__.__name__ == PyMuPDFParser.__name__

    # manually install the plugin with the fake multimodal embedder
    zip_path = create_mock_plugin_zip(flat=True, plugin_id="mock_plugin_multimodal_embedder")
    zip_file_name = zip_path.split("/")[-1]  # mock_plugin_multimodal_embedder.zip in tests/mocks folder
    with open(zip_path, "rb") as f:
        secure_client.post(
            "/plugins/install/upload/",
            files={"file": (zip_file_name, f, "application/zip")},
            headers=secure_client_headers
        )
    # activate for the new agent
    secure_client.put(
        "/plugins/toggle/mock_plugin_multimodal_embedder",
        headers=secure_client_headers | {"X-Agent-ID": cheshire_cat.agent_key}
    )

    # now, change the embedder with the fake multimodal one
    new_embedder = "EmbedderMultimodalDumbConfig"
    response = secure_client.put(
        f"/embedder/settings/{new_embedder}", json={}, headers=secure_client_headers
    )
    assert response.status_code == 200

    file_handlers = cheshire_cat.file_handlers
    assert "application/pdf" in file_handlers
    assert "multimodality" in lizard.plugin_manager.plugins.keys()
    assert file_handlers["application/pdf"].__class__.__name__ == UnstructuredParser.__name__
    assert file_handlers["application/pdf"].document_loader_type == UnstructuredPDFLoader
