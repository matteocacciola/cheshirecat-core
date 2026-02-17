"""
Hook to handle operations for plugins.

This module provides functionality to define hooks that can be triggered after operations on plugins.
"""

from typing import Dict, Any

from cat import hook


@hook(priority=0)
def after_plugin_settings_update(plugin_id: str, settings: Dict[str, Any], cat) -> None:
    """
    Hook triggered after plugin settings are updated.

    This function is executed after the plugin's settings have been updated to allow any post-update operations to be
    performed.

    Args:
        plugin_id: str
            The unique identifier of the plugin whose settings were updated.
        settings: Dict[str, Any]
            The updated plugin settings.
        cat:
            A contextual object or dependency required for post-update processing.
    """
    pass
