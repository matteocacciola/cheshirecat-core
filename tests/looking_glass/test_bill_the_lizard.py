import pytest

from cat.looking_glass import MadHatter
from cat.rabbit_hole import RabbitHole
from cat.services.factory.auth_handler import CoreAuthHandler
from cat.services.websocket_manager import WebSocketManager

from tests.utils import get_class_from_decorated_singleton


def test_main_modules_loaded(lizard):
    assert isinstance(lizard.plugin_manager, MadHatter)
    assert isinstance(lizard.rabbit_hole, get_class_from_decorated_singleton(RabbitHole))
    assert isinstance(lizard.core_auth_handler, CoreAuthHandler)
    assert isinstance(lizard.websocket_manager, WebSocketManager)


@pytest.mark.asyncio
async def test_shutdown(lizard):
    await lizard.shutdown()

    assert lizard.plugin_manager is None
    assert lizard.rabbit_hole is None
    assert lizard.core_auth_handler is None
    assert lizard.websocket_manager is None
