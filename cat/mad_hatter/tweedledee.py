from typing import Dict, List

from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.plugin import Plugin
from cat.mad_hatter.tweedledum import Tweedledum


class Tweedledee(MadHatter):
    """
    Tweedledee is the plugin manager of the various instance of Cheshire Cat. It is responsible for:
    - Activating a plugin at an agent level
    - Deactivating a plugin at an agent level

    Args:
    -----
    config_key: str
        The key to use to store the active plugins in the database settings. Default is DEFAULT_SYSTEM_KEY.
    """
    def __init__(self, agent_key: str):
        self.__agent_key = agent_key

        super().__init__()

    def has_custom_endpoint(self, path: str, methods: set[str] | List[str] | None = None):
        """
        Check if an endpoint with the given path and methods exists in the active plugins.

        Args:
            path (str): The path of the endpoint to check.
            methods (set[str] | List[str] | None): The HTTP methods of the endpoint to check. If None, checks all methods.

        Returns:
            bool: True if the endpoint exists, False otherwise.
        """
        for plugin in self.plugins.values():
            # Check if the plugin has an endpoint with the given path and methods
            for ep in plugin.endpoints:
                if ep.real_path == path and (methods is None or set(ep.methods) == set(methods)):
                    return True

        return False

    def find_plugins(self):
        self.plugins = {}

        self.active_plugins = self.load_active_plugins_ids_from_db()

        # plugins are already loaded when BillTheLizard is created; since its plugin manager scans the plugins folder
        # then, we just need to grab the plugins from there
        for plugin_id in self.available_plugins.keys():
            if plugin_id not in self.active_plugins:
                continue

            if plugin_id not in self.plugins.keys():
                self.plugins[plugin_id] = self.available_plugins[plugin_id]
            try:
                self.plugins[plugin_id].activate_settings(self.agent_key)
            except Exception as e:
                # Couldn't activate the plugin -> Deactivate it
                self.toggle_plugin(plugin_id)
                raise e

        self._on_finish_finding_plugins()

    def plugin_exists(self, plugin_id: str):
        return plugin_id in self.available_plugins.keys()

    def on_plugin_activation(self, plugin_id: str):
        if plugin_id in self.plugins.keys():
            return

        self.plugins[plugin_id] = self.available_plugins[plugin_id]

        # Activate the plugin
        self.plugins[plugin_id].activate_settings(self.agent_key)

    def on_plugin_deactivation(self, plugin_id: str):
        if plugin_id == self.get_base_core_plugin_id or plugin_id not in self.plugins.keys():
            return

        # Deactivate the plugin
        self.plugins[plugin_id].deactivate_settings(self.agent_key)
        self.plugins.pop(plugin_id, None)

    # activate / deactivate plugin
    def toggle_plugin(self, plugin_id: str):
        if plugin_id == self.get_base_core_plugin_id:
            raise Exception("base_plugin cannot be deactivated")

        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not active in the system")

        # update list of active plugins
        if plugin_id in self.active_plugins:
            self.deactivate_plugin(plugin_id)
        else:
            self.activate_plugin(plugin_id)

    @property
    def agent_key(self) -> str:
        return self.__agent_key

    @property
    def available_plugins(self) -> Dict[str, Plugin]:
        # the `plugins` property of the plugin manager of BillTheLizard contains only the globally active plugins
        return Tweedledum().plugins
