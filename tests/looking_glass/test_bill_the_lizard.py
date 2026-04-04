from cat.looking_glass import MadHatter
from cat.rabbit_hole import RabbitHole
from cat.services.factory.auth_handler import CoreAuthHandler
from cat.services.websocket_manager import WebSocketManager


def test_main_modules_loaded(lizard):
    assert isinstance(lizard.plugin_manager, MadHatter)
    assert isinstance(lizard.rabbit_hole, RabbitHole)
    assert isinstance(lizard.core_auth_handler, CoreAuthHandler)
    assert isinstance(lizard.websocket_manager, WebSocketManager)
