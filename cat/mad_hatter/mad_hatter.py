import glob
import os
from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
from typing import List, Dict, Any

from cat import utils
from cat.db.cruds import settings as crud_settings
from cat.db.models import Setting
from cat.log import log
from cat.mad_hatter.decorators import CustomEndpoint, CatHook
from cat.mad_hatter.plugin import Plugin
from cat.mad_hatter.procedures import CatProcedure


class MadHatter(ABC):
    """
    This is the abstract class that defines the methods that the plugin managers should implement.
    """
    def __init__(self):
        from cat.looking_glass.humpty_dumpty import HumptyDumpty

        self.dispatcher = HumptyDumpty()
        self._skip_folders = ["__pycache__", "lost+found"]

        self.plugins: Dict[str, Plugin] = {}

        # a unified registry for all procedures (local tools, forms, remote clients)
        self.procedures_registry: Dict[str, CatProcedure] = {}
        # dict of active plugins hooks (hook_name -> [CatHook, CatHook, ...])
        self.hooks: Dict[str, List[CatHook]] = {}
        # list of active plugins endpoints
        self.endpoints: List[CustomEndpoint] = []

        self.active_plugins: List[str] = []

    # discover all plugins
    def discover_plugins(self):
        # emptying the plugin dictionary, plugins will be discovered from the disk
        # and stored in a dictionary plugin_id -> plugin_obj
        self.plugins = {}

        # plugins are found in the plugins folder,
        # plus the default core plugin (where default hooks and tools are defined)
        # plugin folder is "cat/plugins/" in production, "tests/mocks/mock_plugin_folder/" during tests
        self.active_plugins = self.load_active_plugins_ids_from_db()

        self._on_discovering_plugins()
        self._on_finish_discovering_plugins()

    def load_active_plugins_ids_from_db(self) -> List[str]:
        active_plugins_from_db = crud_settings.get_setting_by_name(self.agent_key, "active_plugins")
        active_plugins: List[str] = [] if active_plugins_from_db is None else active_plugins_from_db["value"]

        if not active_plugins:
            # the core plugins should be appended when the agent is created, i.e. has no active plugins in db
            active_plugins.extend(self.get_core_plugins_ids)

        # ensure base_plugin is always active
        active_plugins.append(self.get_base_core_plugin_id)

        # Remove duplicates
        active_plugins = list(set(active_plugins))

        # Ensure base_factory is first
        if self.get_base_core_plugin_id in active_plugins:
            active_plugins.remove(self.get_base_core_plugin_id)
        active_plugins.insert(0, self.get_base_core_plugin_id)

        return active_plugins

    def activate_plugin(self, plugin_id: str, dispatch_events: bool = True):
        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not present in plugins folder")

        if dispatch_events:
            self.dispatcher.dispatch("on_start_plugin_activate", plugin_id=plugin_id)

        if self.on_plugin_activation(plugin_id=plugin_id):
            # Add the plugin in the list of active plugins
            self.active_plugins.append(plugin_id)

        self._on_finish_discovering_plugins()
        if dispatch_events:
            self.dispatcher.dispatch("on_end_plugin_activate", plugin_id=plugin_id)

    def deactivate_plugin(self, plugin_id: str, dispatch_events: bool = True):
        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not present in plugins folder")

        if plugin_id not in self.active_plugins or plugin_id == self.get_base_core_plugin_id:
            return

        if dispatch_events:
            self.dispatcher.dispatch("on_start_plugin_deactivate", plugin_id=plugin_id)

        # Deactivate the plugin
        log.warning(f"Toggle plugin '{plugin_id}' for agent '{self.agent_key}': Deactivate")
        if self.on_plugin_deactivation(plugin_id=plugin_id):
            # Remove the plugin from the list of active plugins
            self.active_plugins.remove(plugin_id)

            if plugin_id == self.get_base_core_plugin_id or plugin_id not in self.plugins.keys():
                return

            self.plugins.pop(plugin_id, None)

        self._on_finish_discovering_plugins()
        if dispatch_events:
            self.dispatcher.dispatch("on_end_plugin_deactivate", plugin_id=plugin_id)

    # activate / deactivate plugin
    def toggle_plugin(self, plugin_id: str):
        if plugin_id == self.get_base_core_plugin_id:
            raise Exception("base_plugin cannot be deactivated")

        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not active in the system")

        if plugin_id in self.active_plugins:
            self.deactivate_plugin(plugin_id)
        else:
            self.activate_plugin(plugin_id)

    def _on_finish_discovering_plugins(self):
        # store active plugins in db
        active_plugins = list(set(self.active_plugins))
        crud_settings.upsert_setting_by_name(self.agent_key, Setting(name="active_plugins", value=active_plugins))

        log.info(f"Agent '{self.agent_key}' - ACTIVE PLUGINS:")
        log.info(self.active_plugins)

        # update cache and embeddings
        self.hooks = {}
        self.procedures_registry = {}
        self.endpoints = []

        for plugin_id in self.active_plugins:
            plugin = self.plugins[plugin_id]
            # Load local tools, forms and mcp clients as procedures
            self.procedures_registry |= {p.name: p for p in plugin.procedures}
            self.endpoints += plugin.endpoints

            # cache hooks (indexed by hook name)
            for h in plugin.hooks:
                self.hooks.setdefault(h.name, []).append(h)

        # sort each hooks list by priority
        for hook_name in self.hooks.keys():
            self.hooks[hook_name].sort(key=lambda x: x.priority, reverse=True)

        # notify sync has finished
        self.dispatcher.dispatch("on_finish_plugins_sync", self.manage_endpoints)

    # execute requested hook
    def execute_hook(self, hook_name: str, *args, obj) -> Any:
        if hook_name not in self.hooks.keys():
            raise Exception(f"Hook {hook_name} not present in any plugin")

        if len(args) == 0:
            for hook in self.hooks[hook_name]:
                try:
                    log.debug(f"Executing {hook.plugin_id}::{hook.name} with priority {hook.priority}")
                    hook.function(**{self.context_execute_hook: obj})
                except Exception as e:
                    log.error(f"Error in plugin {hook.plugin_id}::{hook.name}: {e}")
                    plugin_obj = self.plugins[hook.plugin_id]
                    log.warning(plugin_obj.plugin_specific_error_message())
            return None

        tea_cup = deepcopy(args[0])

        # run hooks
        for hook in self.hooks[hook_name]:
            try:
                log.debug(f"Executing {hook.plugin_id}::{hook.name} with priority {hook.priority}")
                tea_spoon = hook.function(deepcopy(tea_cup), *deepcopy(args[1:]), **{self.context_execute_hook: obj})
                if tea_spoon is not None:
                    tea_cup = tea_spoon
            except Exception as e:
                log.error(f"Error in plugin {hook.plugin_id}::{hook.name}: {e}")

        return tea_cup

    def get_plugin(self):
        name = utils.inspect_calling_folder()
        return self.plugins[name]

    def _get_plugin_folder_path(self, plugin_id: str) -> str:
        return os.path.join(
            utils.get_core_plugins_path() if plugin_id in self.get_core_plugins_ids else utils.get_plugins_path(),
            plugin_id
        )

    def load_plugin(self, plugin_id: str) -> Plugin | None:
        try:
            folder = self._get_plugin_folder_path(plugin_id)
            return Plugin(folder)
        except Exception as e:
            log.error(str(e))
            return None

    def load_active_plugins_ids_from_folders(self):
        all_plugin_folders = list(set(
            glob.glob(f"{utils.get_core_plugins_path()}/*/") + glob.glob(f"{utils.get_plugins_path()}/*/")
        ))

        plugins = [
            plugin_id
            for folder in all_plugin_folders
            if ((plugin_id := os.path.basename(os.path.normpath(folder))) not in self._skip_folders)
        ]

        # Ensure base_factory is first
        if self.get_base_core_plugin_id in plugins:
            plugins.remove(self.get_base_core_plugin_id)
        plugins.insert(0, self.get_base_core_plugin_id)

        return plugins

    # check if plugin exists
    def plugin_exists(self, plugin_id: str):
        return plugin_id in self.load_active_plugins_ids_from_folders()

    @property
    def procedures(self) -> List[CatProcedure]:
        return list(self.procedures_registry.values())

    @property
    def get_base_core_plugin_id(self) -> str:
        return "base_plugin"

    @property
    def get_core_plugins_ids(self) -> List[str]:
        path = Path(utils.get_core_plugins_path())
        core_plugins = [p.name for p in path.iterdir() if p.is_dir()]
        return core_plugins

    @abstractmethod
    def _on_discovering_plugins(self):
        pass

    @abstractmethod
    def on_plugin_activation(self, plugin_id: str) -> bool:
        pass

    @abstractmethod
    def on_plugin_deactivation(self, plugin_id: str) -> bool:
        pass

    @property
    @abstractmethod
    def agent_key(self) -> str:
        pass

    @property
    @abstractmethod
    def available_plugins(self) -> Dict[str, Plugin]:
        pass

    @property
    @abstractmethod
    def context_execute_hook(self) -> str:
        pass

    @property
    @abstractmethod
    def manage_endpoints(self) -> bool:
        pass
