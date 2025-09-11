from abc import ABC, abstractmethod
from copy import deepcopy
from pathlib import Path
from typing import List, Dict, Any

from cat.db.cruds import settings as crud_settings
from cat.db.models import Setting
from cat.experimental.form.cat_form import CatForm
from cat.log import log
from cat.mad_hatter.decorators import CustomEndpoint, CatHook, CatTool
from cat.mad_hatter.plugin import Plugin
from cat.mad_hatter.procedures import CatProcedure
import cat.utils as utils


class MadHatter(ABC):
    """
    This is the abstract class that defines the methods that the plugin managers should implement.
    """
    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}  # plugins dictionary

        self.hooks: Dict[str, List[CatHook]] = {}  # dict of active plugins hooks (hook_name -> [CatHook, CatHook, ...])
        self.tools: List[CatTool] = []  # list of active plugins tools
        self.forms: List[CatForm] = []  # list of active plugins forms
        self.endpoints: List[CustomEndpoint] = []  # list of active plugins endpoints

        self.active_plugins: List[str] = []

        # this callback is set from outside to be notified when plugin sync is completed
        self.on_finish_plugins_sync_callback = lambda: None

        # this callback is set from outside to be notified when plugin toggle is completed
        self.on_end_plugin_toggle_callback = lambda plugin_id, endpoints, what: None

    # Load hooks, tools and forms of the active plugins into the plugin manager
    def _sync_hooks_tools_and_forms(self):
        # emptying tools, hooks and forms
        self.hooks = {}
        self.tools = []
        self.forms = []
        self.endpoints = []

        for plugin_id in self.active_plugins:
            plugin = self.plugins[plugin_id]
            # load hooks, tools, forms and endpoints from active plugins
            # cache tools
            self.tools += plugin.tools
            self.forms += plugin.forms
            self.endpoints += plugin.endpoints

            # cache hooks (indexed by hook name)
            for h in plugin.hooks:
                self.hooks.setdefault(h.name, []).append(h)

        # sort each hooks list by priority
        for hook_name in self.hooks.keys():
            self.hooks[hook_name].sort(key=lambda x: x.priority, reverse=True)

        # notify sync has finished
        utils.dispatch(self.on_finish_plugins_sync_callback)

    def get_core_plugins_ids(self) -> List[str]:
        path = Path(utils.get_core_plugins_path())
        core_plugins = [p.name for p in path.iterdir() if p.is_dir()]
        return core_plugins

    def load_active_plugins_from_db(self) -> List[str]:
        active_plugins_from_db = crud_settings.get_setting_by_name(self.agent_key, "active_plugins")
        active_plugins: List[str] = [] if active_plugins_from_db is None else active_plugins_from_db["value"]

        if not active_plugins:
            # the core plugins should be appended when the agent is created, i.e. has no active plugins in db
            active_plugins.extend(self.get_core_plugins_ids())

        # ensure base_plugin is always active
        active_plugins.append(self.get_base_core_plugin_id)

        return list(set(active_plugins))  # remove duplicates

    def deactivate_plugin(self, plugin_id: str):
        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not present in plugins folder")

        # update list of active plugins, `base_plugin` cannot be deactivated
        if plugin_id not in self.active_plugins or plugin_id == self.get_base_core_plugin_id:
            return

        # Deactivate the plugin
        log.warning(f"Toggle plugin '{plugin_id}' for agent '{self.agent_key}': Deactivate")

        # Remove the plugin from the list of active plugins
        self.active_plugins.remove(plugin_id)

        self.on_plugin_deactivation(plugin_id=plugin_id)
        self._on_finish_toggle_plugin()

    def activate_plugin(self, plugin_id: str):
        if not self.plugin_exists(plugin_id):
            raise Exception(f"Plugin {plugin_id} not present in plugins folder")

        if plugin_id in self.active_plugins:
            return

        log.warning(f"Toggle plugin '{plugin_id}' for agent '{self.agent_key}': Activate")

        self.on_plugin_activation(plugin_id=plugin_id)

        # Add the plugin in the list of active plugins
        self.active_plugins.append(plugin_id)

        self._on_finish_toggle_plugin()

    def _on_finish_toggle_plugin(self):
        # update DB with list of active plugins, delete duplicate plugins
        active_plugins = list(set(self.active_plugins))
        crud_settings.upsert_setting_by_name(self.agent_key, Setting(name="active_plugins", value=active_plugins))

        # update cache and embeddings
        self._sync_hooks_tools_and_forms()

    def _on_finish_finding_plugins(self):
        # store active plugins in db
        crud_settings.upsert_setting_by_name(
            self.agent_key, Setting(name="active_plugins", value=self.active_plugins)
        )

        log.info(f"Agent '{self.agent_key}' - ACTIVE PLUGINS:")
        log.info(self.active_plugins)

        self._sync_hooks_tools_and_forms()

    # execute requested hook
    def execute_hook(self, hook_name: str, *args, cat) -> Any:
        # check if hook is supported
        if hook_name not in self.hooks.keys():
            raise Exception(f"Hook {hook_name} not present in any plugin")

        # Hook has no arguments (aside cat)
        #  no need to pipe
        if len(args) == 0:
            for hook in self.hooks[hook_name]:
                try:
                    log.debug(
                        f"Executing {hook.plugin_id}::{hook.name} with priority {hook.priority}"
                    )
                    hook.function(cat=cat)
                except Exception as e:
                    log.error(f"Error in plugin {hook.plugin_id}::{hook.name}: {e}")
                    plugin_obj = self.plugins[hook.plugin_id]
                    log.warning(plugin_obj.plugin_specific_error_message())
            return None

        # Hook with arguments.
        #  First argument is passed to `execute_hook` is the pipeable one.
        #  We call it `tea_cup` as every hook called will receive it as an input,
        #  can add sugar, milk, or whatever, and return it for the next hook
        tea_cup = deepcopy(args[0])

        # run hooks
        for hook in self.hooks[hook_name]:
            try:
                # pass tea_cup to the hooks, along other args
                # hook has at least one argument, and it will be piped
                log.debug(
                    f"Executing {hook.plugin_id}::{hook.name} with priority {hook.priority}"
                )
                tea_spoon = hook.function(
                    deepcopy(tea_cup), *deepcopy(args[1:]), cat=cat
                )
                # log.debug(f"Hook {hook.plugin_id}::{hook.name} returned {tea_spoon}")
                if tea_spoon is not None:
                    tea_cup = tea_spoon
            except Exception as e:
                log.error(f"Error in plugin {hook.plugin_id}::{hook.name}: {e}")
                plugin_obj = self.plugins[hook.plugin_id]
                log.warning(plugin_obj.plugin_specific_error_message())

        # tea_cup has passed through all hooks. Return final output
        return tea_cup

    # get plugin object (used from within a plugin)
    def get_plugin(self):
        name = utils.inspect_calling_folder()
        return self.plugins[name]

    @property
    def procedures(self) -> List[CatProcedure]:
        return self.tools + self.forms

    @property
    def get_base_core_plugin_id(self) -> str:
        return "base_plugin"

    @abstractmethod
    def plugin_exists(self, plugin_id: str):
        pass

    @abstractmethod
    def find_plugins(self):
        pass

    @abstractmethod
    def toggle_plugin(self, plugin_id: str):
        pass

    @abstractmethod
    def on_plugin_activation(self, plugin_id: str):
        pass

    @abstractmethod
    def on_plugin_deactivation(self, plugin_id: str):
        pass

    @abstractmethod
    def _load_plugin(self, plugin_path: str) -> bool:
        pass

    @property
    @abstractmethod
    def agent_key(self):
        pass
