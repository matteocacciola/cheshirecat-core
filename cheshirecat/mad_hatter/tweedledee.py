from typing import Dict, List

from cheshirecat.log import log
from cheshirecat.mad_hatter.mad_hatter import MadHatter
from cheshirecat.mad_hatter.plugin import Plugin
from cheshirecat.mad_hatter.tweedledum import Tweedledum


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

        self.active_plugins = self.load_active_plugins_from_db()
        log.info(f"Agent '{self.agent_key}' - ACTIVE PLUGINS:")
        log.info(self.active_plugins)

        # plugins are already loaded when BillTheLizard is created; since its plugin manager scans the plugins folder
        # then, we just need to grab the plugins from there
        for plugin_id in self.system_plugins.keys():
            if plugin_id not in self.active_plugins:
                continue

            self._load_plugin(plugin_id)
            try:
                self.plugins[plugin_id].activate_settings(self.agent_key)
            except Exception as e:
                # Couldn't activate the plugin -> Deactivate it
                self.toggle_plugin(plugin_id)
                raise e

        self._sync_hooks_tools_and_forms()

    def plugin_exists(self, plugin_id: str):
        return plugin_id in self.system_plugins.keys()

    def __local_plugin_exists(self, plugin_id: str):
        return plugin_id in self.plugins.keys()

    def _load_plugin(self, plugin_id: str) -> bool:
        if self.__local_plugin_exists(plugin_id):
            return False

        self.plugins[plugin_id] = self.system_plugins[plugin_id]
        return True

    def on_plugin_activation(self, plugin_id: str):
        self._load_plugin(plugin_id)

        # Activate the plugin
        self.plugins[plugin_id].activate_settings(self.agent_key)

    def on_plugin_deactivation(self, plugin_id: str):
        if plugin_id == "core_plugin" or not self.__local_plugin_exists(plugin_id):
            return

        # Deactivate the plugin
        self.plugins[plugin_id].deactivate_settings(self.agent_key)
        self.plugins.pop(plugin_id, None)

    # activate / deactivate plugin
    def toggle_plugin(self, plugin_id: str):
        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not present in plugins folder")

        plugin_is_active = plugin_id in self.active_plugins

        # update list of active plugins
        if plugin_is_active:
            self.deactivate_plugin(plugin_id)
        else:
            self.activate_plugin(plugin_id)

    @property
    def system_plugins(self) -> Dict[str, Plugin]:
        return Tweedledum().plugins

    @property
    def agent_key(self):
        return self.__agent_key
