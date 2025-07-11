import os
import sys
import json
import glob
import tempfile
import importlib
import subprocess
from typing import Dict, List, Tuple
from inspect import getmembers, isclass
from pydantic import BaseModel, ValidationError
from packaging.requirements import Requirement

from cat.db.cruds import plugins as crud_plugins
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.experimental.form.cat_form import CatForm
from cat.mad_hatter.decorators import CustomEndpoint, CatHook, CatPluginDecorator, CatTool
from cat.utils import to_camel_case, inspect_calling_agent, get_py_filename_dotted_notation
from cat.log import log


# Empty class to represent basic plugin Settings model
class PluginSettingsModel(BaseModel):
    pass


# this class represents a plugin in memory
# the plugin itself is managed as much as possible unix style
#      (i.e. by saving information in the folder itself)


class Plugin:
    def __init__(self, plugin_path: str):
        # does folder exist?
        if not os.path.exists(plugin_path) or not os.path.isdir(plugin_path):
            raise Exception(
                f"{plugin_path} does not exist or is not a folder. Cannot create Plugin."
            )

        # where the plugin is on disk
        self._path: str = plugin_path

        # search for .py files in folder
        py_files_path = os.path.join(self._path, "**/*.py")
        self._py_files = glob.glob(py_files_path, recursive=True)

        if len(self._py_files) == 0:
            raise Exception(
                f"{plugin_path} does not contain any python files. Cannot create Plugin."
            )

        # plugin id is just the folder name
        self._id: str = os.path.basename(os.path.normpath(plugin_path))

        # plugin manifest (name, description, thumb, etc.)
        self._manifest = self._load_manifest()

        # list of tools, forms and hooks contained in the plugin.
        # The plugin manager will cache them for easier access,
        # but they are created and stored in each plugin instance
        self._hooks: List[CatHook] = []  # list of plugin hooks
        self._tools: List[CatTool] = []  # list of plugin tools
        self._forms: List[CatForm] = []  # list of plugin forms
        self._endpoints: List[CustomEndpoint] = []  # list of plugin endpoints

        # list of @plugin decorated functions overriding default plugin behaviour
        self._plugin_overrides: Dict[str, CatPluginDecorator] = {}

        # plugin starts deactivated
        self._active = False

    def activate(self, agent_id: str):
        # install plugin requirements on activation
        try:
            self._install_requirements()
        except Exception as e:
            raise e

        self.activate_settings(agent_id, False)

        # run custom activation from @plugin
        if "activated" in self.overrides:
            self.overrides["activated"].function(self)

    def activate_settings(self, agent_id: str, incremental: bool = True):
        # load hooks and tools
        self._load_decorated_functions()

        # by default, plugin settings are saved inside the Redis database
        setting = crud_plugins.get_setting(agent_id, self._id)

        # store the new settings incrementally, without losing the values of the configurations still supported
        if incremental:
            self._migrate_settings(agent_id, setting)
        else:
            # try to create the setting into the Redis database
            if not setting:
                self._create_settings_from_model(agent_id)

        self._active = True

    def deactivate(self, agent_id: str):
        # run custom deactivation from @plugin
        if "deactivated" in self.overrides:
            self.overrides["deactivated"].function(self)

        # Remove the imported modules
        for py_file in self._py_files:
            py_filename = py_file.replace("/", ".").replace(".py", "")

            # If the module is imported it is removed
            if py_filename not in sys.modules:
                continue
            log.debug(f"Remove module {py_filename}")
            sys.modules.pop(py_filename)

        self.deactivate_settings(agent_id)

    def deactivate_settings(self, agent_id: str):
        self._hooks = []
        self._tools = []
        self._forms = []

        for endpoint in self._endpoints:
            endpoint.deactivate()
        self._endpoints = []

        self._plugin_overrides = {}
        self._active = False

        # remove the settings
        crud_plugins.delete_setting(agent_id, self._id)

    # get plugin settings JSON schema
    def settings_schema(self):
        # is "settings_schema" hook defined in the plugin?
        if "settings_schema" in self.overrides:
            return self.overrides["settings_schema"].function()

        # otherwise, if the "settings_schema" is not defined but "settings_model" is, it gets the schema from the model
        if "settings_model" in self.overrides:
            return self.overrides["settings_model"].function().model_json_schema()

        # default schema (empty)
        return PluginSettingsModel.model_json_schema()

    # get plugin settings Pydantic model
    def settings_model(self):
        # is "settings_model" hook defined in the plugin?
        if "settings_model" in self.overrides:
            return self.overrides["settings_model"].function()

        # is "settings_schema" hook defined in the plugin?
        if "settings_schema" in self.overrides:
            schema = self.overrides["settings_schema"].function()
            pydantic_class = schema.get("__pydantic_model__", schema.get("title"))
            if not pydantic_class:
                return PluginSettingsModel

            if isinstance(pydantic_class, BaseModel):
                return pydantic_class

            if not isinstance(pydantic_class, str):
                log.error(f"Invalid settings class {pydantic_class} from `settings_schema` hook in plugin {self.id}")
                return PluginSettingsModel

            # if the pydantic class is a string, try to load it from the plugin
            # find where a Pydantic model with name pydantic_class is defined within the folder self._path
            for py_file in self._py_files:
                py_filename = get_py_filename_dotted_notation(py_file)
                try:
                    module = importlib.import_module(py_filename)
                    if hasattr(module, pydantic_class):
                        return getattr(module, pydantic_class)
                except Exception:
                    pass

            # if the pydantic class is not found, return the default PluginSettingsModel
            log.error(f"Unable to find settings model {pydantic_class} from `settings_schema` hook in plugin {self.id}")

        # default schema (empty)
        return PluginSettingsModel

    # load plugin settings
    def load_settings(self, agent_id: str | None = None):
        if agent_id is None:
            try:
                calling_agent = inspect_calling_agent()
                agent_id = calling_agent.id
            except Exception as e:
                log.error(f"Error loading plugin {self._id} settings. Getting default settings: {e}")
                log.warning(self.plugin_specific_error_message())
                agent_id = DEFAULT_SYSTEM_KEY

        # is "settings_load" hook defined in the plugin?
        if "load_settings" in self.overrides:
            return self.overrides["load_settings"].function()

        # by default, plugin settings are saved inside the Redis database
        settings = crud_plugins.get_setting(agent_id, self._id)
        if not settings and not self._create_settings_from_model(agent_id):
            return {}

        # load settings from Redis database, in case of new settings, the already grabbed values are loaded otherwise
        settings = settings if settings else crud_plugins.get_setting(agent_id, self._id)
        try:
            # Validate the settings
            self.settings_model().model_validate(settings)
            return settings
        except Exception as e:
            log.error(f"Unable to load plugin {self._id} settings: {e}")
            log.warning(self.plugin_specific_error_message())
            raise e

    # save plugin settings
    def save_settings(self, settings: Dict, agent_id: str):
        # is "settings_save" hook defined in the plugin?
        if "save_settings" in self.overrides:
            return self.overrides["save_settings"].function(settings)

        try:
            # overwrite settings over old ones
            # write settings into the Redis database
            return crud_plugins.update_setting(agent_id, self._id, settings)
        except Exception as e:
            log.error(f"Unable to save plugin {self._id} settings: {e}")
            log.warning(self.plugin_specific_error_message())
            return {}

    def _get_settings_from_model(self) -> Dict | None:
        try:
            model = self.settings_model()
            # if some settings have no default value this will raise a ValidationError
            settings = model().model_dump()

            return settings
        except ValidationError:
            return None

    def _create_settings_from_model(self, agent_id: str) -> bool:
        settings = self._get_settings_from_model()
        if settings is None:
            log.debug(f"{self.id} settings model have missing default values, no settings created")
            return False

        # If each field have a default value and the model is correct, create the settings with default values
        crud_plugins.set_setting(agent_id, self._id, settings)
        log.debug(f"{self.id} have no settings, created with settings model default values")

        return True

    def _migrate_settings(self, agent_id: str, settings: Dict) -> bool:
        # the new setting coming from the model to be activated
        new_setting = self._get_settings_from_model()

        try:
            # store the new settings incrementally, without losing the values of the configurations still supported
            finalized_setting = {k: settings.get(k, v) for k, v in new_setting.items()} if settings else new_setting

            # Validate the settings
            self.settings_model().model_validate(finalized_setting)
        except:
            finalized_setting = new_setting

        # try to create the new incremental settings into the Redis database
        crud_plugins.set_setting(agent_id, self._id, finalized_setting)
        log.info(f"Plugin {self._id} for agent {agent_id}, migrating settings: {finalized_setting}")

        return True

    def _load_manifest(self):
        plugin_json_metadata_file_name = "plugin.json"
        plugin_json_metadata_file_path = os.path.join(
            self._path, plugin_json_metadata_file_name
        )
        meta = {"id": self._id}
        json_file_data = {}

        if os.path.isfile(plugin_json_metadata_file_path):
            try:
                json_file = open(plugin_json_metadata_file_path)
                json_file_data = json.load(json_file)
                json_file.close()
            except:
                log.debug(
                    f"Loading plugin {self._path} metadata, defaulting to generated values"
                )

        meta["name"] = json_file_data.get("name", to_camel_case(self._id))
        meta["description"] = json_file_data.get(
            "description",
            (
                "Description not found for this plugin. "
                f"Please create a `{plugin_json_metadata_file_name}`"
                " in the plugin folder."
            ),
        )
        meta["author_name"] = json_file_data.get("author_name", "Unknown author")
        meta["author_url"] = json_file_data.get("author_url", "")
        meta["plugin_url"] = json_file_data.get("plugin_url", "")
        meta["tags"] = json_file_data.get("tags", "unknown")
        meta["thumb"] = json_file_data.get("thumb", "")
        meta["version"] = json_file_data.get("version", "0.0.1")
        meta["min_cat_version"] = json_file_data.get("min_cat_version", "")
        meta["max_cat_version"] = json_file_data.get("max_cat_version", "")

        return meta

    def _install_requirements(self):
        req_file = os.path.join(self.path, "requirements.txt")
        if not os.path.exists(req_file):
            return

        installed_packages = {x.name for x in importlib.metadata.distributions()}
        filtered_requirements = []
        try:
            with open(req_file, "r") as read_file:
                requirements = read_file.readlines()

            for req in requirements:
                log.info(f"Installing requirements for plugin {self.id}")

                # get package name
                package_name = Requirement(req).name

                # check if package is installed
                if package_name not in installed_packages:
                    filtered_requirements.append(req)
                    continue

                log.debug(f"{package_name} is already installed")
        except Exception as e:
            log.error(f"Error during requirements check: {e}, for {self.id}")

        if len(filtered_requirements) == 0:
            return

        with tempfile.NamedTemporaryFile(mode="w") as tmp:
            tmp.write("".join(filtered_requirements))
            # If flush is not performed, when pip reads the file it is empty
            tmp.flush()

            try:
                subprocess.run(
                    ["pip", "install", "--no-cache-dir", "-r", tmp.name], check=True
                )
            except subprocess.CalledProcessError as e:
                log.error(f"Error while installing plugin {self.id} requirements: {e}")

                # Uninstall the previously installed packages
                log.info(f"Uninstalling requirements for: {self.id}")
                subprocess.run(["pip", "uninstall", "-r", tmp.name], check=True)

                raise Exception(f"Error during plugin {self.id} requirements installation")

    # lists of hooks and tools
    def _load_decorated_functions(self):
        hooks = []
        tools = []
        forms = []
        endpoints = []
        plugin_overrides = []

        for py_file in self._py_files:
            py_filename = get_py_filename_dotted_notation(py_file)

            log.debug(f"Import module {py_filename}")

            # save a reference to decorated functions
            try:
                plugin_module = importlib.import_module(py_filename)
                importlib.reload(plugin_module)

                hooks += getmembers(plugin_module, self.is_cat_hook)
                tools += getmembers(plugin_module, self.is_cat_tool)
                forms += getmembers(plugin_module, self.is_cat_form)
                endpoints += getmembers(plugin_module, self._is_custom_endpoint)
                plugin_overrides += getmembers(
                    plugin_module, self._is_cat_plugin_override
                )
            except Exception as e:
                log.error(
                    f"Error in {py_filename}: {str(e)}. Unable to load plugin {self._id}"
                )
                log.warning(self.plugin_specific_error_message())

        # clean and enrich instances
        self._hooks = list(map(self._clean_hook, hooks))
        self._tools = list(map(self._clean_tool, tools))
        self._forms = list(map(self._clean_form, forms))
        self._endpoints = list(map(self._clean_endpoint, endpoints))
        self._plugin_overrides = {override.name: override for _, override in plugin_overrides}

    def plugin_specific_error_message(self):
        name = self.manifest.get("name")
        url = self.manifest.get("plugin_url")
        if url:
            return f"To resolve any problem related to {name} plugin, contact the creator using github issue at the link {url}"
        return f"Error in {name} plugin, contact the creator"

    def _clean_hook(self, hook: Tuple[str, CatHook]):
        # getmembers returns a tuple
        _, h = hook
        h.plugin_id = self._id
        return h

    def _clean_tool(self, tool: Tuple[str, CatTool]):
        # getmembers returns a tuple
        _, t = tool
        t.plugin_id = self._id
        return t

    def _clean_form(self, form: Tuple[str, CatForm]):
        # getmembers returns a tuple
        _, f = form
        f.plugin_id = self._id
        return f

    def _clean_endpoint(self, endpoint: Tuple[str, CustomEndpoint]):
        # getmembers returns a tuple
        _, e = endpoint
        e.plugin_id = self._id
        return e

    # a plugin hook function has to be decorated with @hook
    # (which returns an instance of CatHook)
    @staticmethod
    def is_cat_hook(obj):
        return isinstance(obj, CatHook)

    @staticmethod
    def is_cat_form(obj):
        if not isclass(obj) or obj is CatForm:
            return False

        if not issubclass(obj, CatForm) or not obj._autopilot:
            return False

        return True

    # a plugin tool function has to be decorated with @tool
    # (which returns an instance of CatTool)
    @staticmethod
    def is_cat_tool(obj):
        return isinstance(obj, CatTool)

    # a plugin override function has to be decorated with @plugin
    # (which returns an instance of CatPluginDecorator)
    @staticmethod
    def _is_cat_plugin_override(obj):
        return isinstance(obj, CatPluginDecorator)

    # a plugin custom endpoint has to be decorated with @endpoint
    # (which returns an instance of CustomEndpoint)
    @staticmethod
    def _is_custom_endpoint(obj):
        return isinstance(obj, CustomEndpoint)

    @property
    def path(self):
        return self._path

    @property
    def id(self):
        return self._id

    @property
    def manifest(self):
        return self._manifest

    @property
    def active(self):
        return self._active

    @property
    def hooks(self):
        return self._hooks

    @property
    def tools(self):
        return self._tools

    @property
    def forms(self):
        return self._forms

    @property
    def endpoints(self):
        return self._endpoints

    @property
    def overrides(self):
        return self._plugin_overrides
