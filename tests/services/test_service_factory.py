import pytest

from cat import EmbedderSettings
from cat.services.service_factory import ServiceFactory


@pytest.mark.asyncio
async def test_get_config_class_from_adapter(lizard):
    embedder = await lizard.embedder()
    sf = ServiceFactory(
        agent_key=lizard.agent_key,
        hook_manager=lizard.plugin_manager,
        factory_allowed_handler_name="factory_allowed_embedders",
        setting_category="embedder",
        schema_name="languageEmbedderName",
    )

    embedder_config = await sf.get_config_class_from_adapter(embedder)

    assert issubclass(embedder_config, EmbedderSettings)  # type: ignore
    assert not embedder_config.is_multimodal()
