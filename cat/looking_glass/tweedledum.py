
import shutil
from typing import List, Dict

from cat import utils
from cat.db.cruds import plugins as crud_plugins
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.log import log
from cat.mad_hatter import MadHatter, Plugin, PluginExtractor
from cat.utils import singleton


@singleton
class Tweedledum(MadHatter):
    """
    Tweedledum is the plugin manager of the Lizard. It is responsible for:
    - Installing a plugin
    - Uninstalling a plugin
    - Loading plugins
    - Prioritizing hooks
    - Executing hooks
    - Activating a plugin at a system level

    Notes:
    ------
    Tweedledum is the one that knows about the plugins, the hooks, the tools and the forms. It is the one that
    executes the hooks and the tools, and the one that loads the forms. It:
    - loads and execute plugins
    - enter into the plugin folder and loads everything that is decorated or named properly
    - orders plugged in hooks by name and priority
    - exposes functionality to the lizard and cats to execute hooks and tools
    """
    def is_custom_endpoint(self, path: str, methods: List[str] | None = None):
        """
        Check if the given path and methods correspond to a custom endpoint.

        Args:
            path (str): The path of the endpoint to check.
            methods (List[str] | None): The HTTP methods of the endpoint to check. If None, checks all methods.

        Returns:
            bool: True if the endpoint is a custom endpoint, False otherwise.
        """
        return any(
            ep.real_path == path and (methods is None or set(ep.methods) == set(methods)) for ep in self.endpoints
        )

    def install_plugin(self, package_plugin: str) -> str:
        """
        Install a plugin from a package file (zip/tar).

        Args:
            package_plugin (str): The path to the plugin package file.

        Returns:
            str: The ID of the installed plugin.
        """
        # extract zip/tar file into plugin folder
        extractor = PluginExtractor(package_plugin)
        plugin_path = extractor.extract(utils.get_plugins_path())
        plugin_id = extractor.id

        # install the extracted plugin
        return self.install_extracted_plugin(plugin_id, plugin_path)

    def install_extracted_plugin(self, plugin_id: str, plugin_path: str) -> str:
        # extract the plugin from the package
        self.dispatcher.dispatch("on_start_plugin_install", plugin_id=plugin_id, plugin_path=plugin_path)

        # create plugin obj, and eventually activate it
        if plugin_id in self.get_core_plugins_ids:
            return plugin_id

        self.activate_plugin(plugin_id)

        # notify uninstallation has finished
        self.dispatcher.dispatch("on_end_plugin_install", plugin_id=plugin_id, plugin_path=plugin_path)

        return plugin_id

    def uninstall_plugin(self, plugin_id: str):
        if not self.plugin_exists(plugin_id) or plugin_id in self.get_core_plugins_ids:
            return

        self.dispatcher.dispatch("on_start_plugin_uninstall", plugin_id=plugin_id)

        endpoints = self.plugins[plugin_id].endpoints
        plugin_path = self.plugins[plugin_id].path

        # deactivate plugin if it is active (will sync cache)
        if plugin_id in self.active_plugins:
            self.deactivate_plugin(plugin_id)

        # remove plugin folder
        shutil.rmtree(plugin_path)

        crud_plugins.destroy_plugin(plugin_id)

        # notify uninstall has finished
        self.dispatcher.dispatch("on_end_plugin_uninstall", plugin_id=plugin_id, endpoints=endpoints)

    def _on_discovering_plugins(self):
        if not self.active_plugins:
            self.active_plugins = self.load_active_plugins_ids_from_folders()

        for plugin_id in self.active_plugins:
            plugin = self.load_plugin(plugin_id)
            if not plugin:
                log.error(f"Plugin {plugin_id} could not be loaded")
                continue

            self.plugins[plugin.id] = plugin
            try:
                self.on_plugin_activation(plugin_id)
            except Exception as e:
                # Couldn't activate the plugin -> Deactivate it
                self.deactivate_plugin(plugin_id)
                self.active_plugins.remove(plugin_id)
                raise e

    def on_plugin_activation(self, plugin_id: str) -> bool:
        plugin = self.load_plugin(plugin_id)
        if not plugin:
            return False

        self.plugins[plugin.id] = plugin

        # Activate the plugin
        try:
            self.plugins[plugin_id].activate(self.agent_key)

            return True
        except Exception as e:
            log.error(f"Could not activate plugin {plugin_id}: {e}")
            self.plugins.pop(plugin_id, None)
            return False

    def on_plugin_deactivation(self, plugin_id: str) -> bool:
        try:
            # Deactivate the plugin
            self.plugins[plugin_id].deactivate(self.agent_key)
            return True
        except Exception as e:
            log.error(f"Could not deactivate plugin {plugin_id}: {e}")
            return False

    @property
    def agent_key(self) -> str:
        return DEFAULT_SYSTEM_KEY

    @property
    def available_plugins(self) -> Dict[str, Plugin]:
        plugins_ids = self.load_active_plugins_ids_from_folders()

        return {
            plugin_id: self.load_plugin(plugin_id) for plugin_id in plugins_ids
        }

    @property
    def context_execute_hook(self):
        return "lizard"
