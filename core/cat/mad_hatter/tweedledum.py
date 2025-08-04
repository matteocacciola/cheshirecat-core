import os
import glob
import shutil
from typing import List, Tuple

from cat.db.cruds import settings as crud_settings, plugins as crud_plugins
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.db.models import Setting
from cat.log import log
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.plugin_extractor import PluginExtractor
from cat.mad_hatter.plugin import Plugin
import cat.utils as utils
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

    def __init__(self):
        self.__skip_folders = ["__pycache__", "lost+found"]
        self.__plugins_folder = utils.get_plugins_path()

        # this callback is set from outside to be notified when plugin install is started
        self.on_start_plugin_install_callback = lambda: None
        # this callback is set from outside to be notified when plugin install is completed
        self.on_end_plugin_install_callback = lambda plugin_id, plugin_path: None

        # this callback is set from outside to be notified when plugin uninstall is started
        self.on_start_plugin_uninstall_callback = lambda plugin_id: None
        # this callback is set from outside to be notified when plugin uninstall is completed
        self.on_end_plugin_uninstall_callback = lambda plugin_id, endpoints: None

        super().__init__()

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
        # extract the plugin from the package
        plugin_id, plugin_path = self.extract_plugin(package_plugin)

        # install the extracted plugin
        return self.install_extracted_plugin(plugin_id, plugin_path)

    def extract_plugin(self, package_plugin: str) -> Tuple[str, str]:
        utils.dispatch_event(self.on_start_plugin_install_callback)

        # extract zip/tar file into plugin folder
        extractor = PluginExtractor(package_plugin)
        plugin_path = extractor.extract(self.__plugins_folder)
        plugin_id = extractor.id

        return plugin_id, plugin_path

    def install_extracted_plugin(self, plugin_id: str, plugin_path: str) -> str:
        # create plugin obj, and eventually activate it
        if plugin_id != "core_plugin" and self._load_plugin(plugin_path):
            # deactivate a plugin on reinstallation
            if plugin_id in self.active_plugins:
                self.deactivate_plugin(plugin_id)

            self.activate_plugin(plugin_id)

        # notify uninstallation has finished
        utils.dispatch_event(self.on_end_plugin_install_callback, plugin_id=plugin_id, plugin_path=plugin_path)

        return plugin_id

    def uninstall_plugin(self, plugin_id: str):
        utils.dispatch_event(self.on_start_plugin_uninstall_callback, plugin_id=plugin_id)

        endpoints = []
        if self.plugin_exists(plugin_id) and plugin_id != "core_plugin":
            endpoints = self.plugins[plugin_id].endpoints

            # deactivate plugin if it is active (will sync cache)
            if plugin_id in self.active_plugins:
                self.deactivate_plugin(plugin_id)

            # remove plugin from cache
            plugin_path = self.plugins[plugin_id].path
            del self.plugins[plugin_id]

            # remove plugin folder
            shutil.rmtree(plugin_path)

        crud_plugins.destroy_plugin(plugin_id)

        # notify uninstall has finished
        utils.dispatch_event(self.on_end_plugin_uninstall_callback, plugin_id=plugin_id, endpoints=endpoints)

    # check if plugin exists
    def plugin_exists(self, plugin_id: str):
        return plugin_id in self.plugins.keys()

    # discover all plugins
    def find_plugins(self):
        # emptying plugin dictionary, plugins will be discovered from disk
        # and stored in a dictionary plugin_id -> plugin_obj
        self.plugins = {}

        # plugins are found in the plugins folder,
        # plus the default core plugin (where default hooks and tools are defined)
        core_plugin_folder = utils.get_base_path() + "mad_hatter/core_plugin/"

        # plugin folder is "cat/plugins/" in production, "tests/mocks/mock_plugin_folder/" during tests
        all_plugin_folders = [core_plugin_folder] + glob.glob(
            f"{self.__plugins_folder}*/"
        )

        # discover plugins, folder by folder
        active_plugins = []
        for folder in all_plugin_folders:
            plugin_id = os.path.basename(os.path.normpath(folder))
            if plugin_id in self.__skip_folders:
                continue

            if not self._load_plugin(folder):
                log.error(f"Plugin {plugin_id} could not be loaded")
                continue

            try:
                self.plugins[plugin_id].activate(self.agent_key)
                active_plugins.append(plugin_id)
            except Exception as e:
                # Couldn't activate the plugin -> Deactivate it
                self.deactivate_plugin(plugin_id)
                raise e

        crud_settings.upsert_setting_by_name(self.agent_key, Setting(name="active_plugins", value=active_plugins))
        self.active_plugins = self.load_active_plugins_from_db()

        log.info("ACTIVE PLUGINS:")
        log.info(self.active_plugins)

        self._sync_hooks_tools_and_forms()

    def _load_plugin(self, plugin_path: str) -> bool:
        # Instantiate plugin.
        #   If the plugin is inactive, only manifest will be loaded
        #   If active, also settings, tools and hooks
        try:
            plugin = Plugin(plugin_path)
            # if plugin is valid, keep a reference
            self.plugins[plugin.id] = plugin
            return True
        except Exception as e:
            # Something happened while loading the plugin.
            # Print the error and go on with the others.
            log.error(str(e))
            return False

    def on_plugin_activation(self, plugin_id: str):
        # Activate the plugin
        self.plugins[plugin_id].activate(self.agent_key)

    def on_plugin_deactivation(self, plugin_id: str):
        # Deactivate the plugin
        self.plugins[plugin_id].deactivate(self.agent_key)

    @property
    def agent_key(self):
        return DEFAULT_SYSTEM_KEY
