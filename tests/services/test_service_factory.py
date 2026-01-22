from cat import EmbedderSettings
from cat.services.service_factory import ServiceFactory


def test_get_config_class_from_adapter(lizard):
    embedder_config = ServiceFactory(
        agent_key=lizard.agent_key,
        hook_manager=lizard.plugin_manager,
        factory_allowed_handler_name="factory_allowed_embedders",
        setting_category="embedder",
        schema_name="languageEmbedderName",
    ).get_config_class_from_adapter(lizard.embedder)

    assert issubclass(embedder_config, EmbedderSettings)
    assert not embedder_config.is_multimodal()
