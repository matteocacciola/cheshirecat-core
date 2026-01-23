import glob
import importlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from inspect import getmembers, isabstract
from pathlib import Path
from typing import Dict, List, Tuple
from packaging.requirements import Requirement
from pydantic import BaseModel, ValidationError

from cat.db.cruds import plugins as crud_plugins
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.log import log
from cat.looking_glass.mad_hatter.decorators.experimental.form import CatForm
from cat.looking_glass.mad_hatter.decorators.experimental.mcp_client import CatMcpClient
from cat.looking_glass.mad_hatter.decorators.endpoint import CatEndpoint
from cat.looking_glass.mad_hatter.decorators.hook import CatHook
from cat.looking_glass.mad_hatter.decorators.plugin_decorator import CatPluginDecorator
from cat.looking_glass.mad_hatter.decorators.tool import CatTool
from cat.looking_glass.mad_hatter.procedures import CatProcedure
from cat.looking_glass.models import PluginSettingsModel, PluginManifest
from cat.utils import inspect_calling_agent, get_base_path, to_camel_case


class Plugin:
    def __init__(self, plugin_path: str):
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

        self._hooks: List[CatHook] = []  # list of plugin hooks
        self._procedures: List[CatProcedure] = []  # list of plugin procedures (tools + forms)
        self._endpoints: List[CatEndpoint] = []  # list of plugin endpoints

        # list of @plugin decorated functions overriding default plugin behaviour
        self._plugin_overrides: Dict[str, CatPluginDecorator] = {}

        # plugin starts deactivated
        self._active = False

    def activate(self, agent_id: str):
        # install plugin requirements on activation
        self._install_requirements()

        # load hooks and tools
        self._load_decorated_functions()

        self.activate_settings(agent_id)
        self._active = True

        # run custom activation from @plugin
        if "activated" in self.overrides:
            self.overrides["activated"].function(self)

    def activate_settings(self, agent_id: str):
        # by default, plugin settings are saved inside the Redis database
        setting = crud_plugins.get_setting(agent_id, self._id)

        # store the new settings incrementally, without losing the values of the configurations still supported
        # the new setting coming from the model to be activated
        new_setting = self._get_settings_from_model()

        if not setting and not new_setting:
            # no settings to migrate
            return True

        if setting is not None and new_setting and setting == new_setting:
            # settings are the same, no need to migrate
            return True

        try:
            # store the new settings incrementally, without losing the values of the configurations still supported
            finalized_setting = {k: setting.get(k, v) for k, v in new_setting.items()} if setting else new_setting

            # Validate the settings
            self.settings_model().model_validate(finalized_setting)
        except:
            finalized_setting = new_setting

        if setting == finalized_setting:
            # no settings to migrate
            return True

        # try to create the new incremental settings into the Redis database
        crud_plugins.set_setting(agent_id, self._id, finalized_setting)
        log.info(f"Plugin {self._id} for agent '{agent_id}', settings migrated from {setting} to {finalized_setting}")

        return True

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

        self._unload_decorated_functions()
        self._active = False
        self.deactivate_settings(agent_id)

    def deactivate_settings(self, agent_id: str):
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

    def _get_py_filename_dotted_notation(self, py_file: str) -> str:
        base_path_dotted_notation = get_base_path().replace("/", ".")
        return (
            py_file.replace(".py", "")
            .replace("/", ".")
            .replace(base_path_dotted_notation, "cat.")
        )

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
                py_filename = self._get_py_filename_dotted_notation(py_file)
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
                agent_id = calling_agent.agent_key
            except Exception as e:
                log.error(f"Error loading plugin {self._id} settings. Getting default settings: {e}")
                log.warning(self.plugin_specific_error_message())
                agent_id = DEFAULT_SYSTEM_KEY

        # is "load_settings" hook defined in the plugin?
        if "load_settings" in self.overrides:
            return self.overrides["load_settings"].function(self._id, agent_id)

        # by default, plugin settings are saved inside the Redis database
        settings = crud_plugins.get_setting(agent_id, self._id) or self._get_settings_from_model()
        if settings is None:
            log.debug(f"{self.id} settings model have missing default values, no settings created")
            return {}

        # If each field have a default value and the model is correct, create the settings with default values
        crud_plugins.set_setting(agent_id, self._id, settings)
        log.debug(f"{self.id} have no settings, created with settings model default values")

        # load settings from Redis database, in case of new settings, the already grabbed values are loaded otherwise
        settings = settings if settings else (crud_plugins.get_setting(agent_id, self._id) or {})
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
            return self.overrides["save_settings"].function(self._id, settings, agent_id)

        try:
            # overwrite settings over old ones
            # write settings into the Redis database
            return crud_plugins.update_setting(agent_id, self._id, settings)
        except Exception as e:
            log.error(f"Unable to save plugin {self._id} settings: {e}")
            log.warning(self.plugin_specific_error_message())
            return {}

    def missing_dependencies(self, available_plugins: List[str]) -> List[str]:
        if not self.manifest.dependencies:
            return []

        missing_dependencies = [
            dependency for dependency in self.manifest.dependencies if dependency not in available_plugins
        ]
        if missing_dependencies:
            log.error(f"Plugin {self.id} is missing dependencies: {missing_dependencies}")

        return missing_dependencies

    def _get_settings_from_model(self) -> Dict | None:
        try:
            model = self.settings_model()
            # if some settings have no default value this will raise a ValidationError
            settings = model().model_dump()

            return settings
        except ValidationError:
            return None

    def _load_manifest(self) -> PluginManifest:
        plugin_json_metadata_file_name = "plugin.json"
        plugin_json_metadata_file_path = os.path.join(
            self._path, plugin_json_metadata_file_name
        )
        json_file_data = {}

        if os.path.isfile(plugin_json_metadata_file_path):
            try:
                json_file = open(plugin_json_metadata_file_path)
                json_file_data = json.load(json_file)
                json_file.close()
            except Exception:
                log.error(
                    f"Loading plugin {self._path} metadata, defaulting to generated values"
                )

        json_file_data["id"] = self._id
        json_file_data["name"] = json_file_data.get("name", to_camel_case(self._id))
        return PluginManifest(**json_file_data)

    def _install_requirements(self):
        req_file = os.path.join(self.path, "requirements.txt")
        if not os.path.exists(req_file):
            return

        installed_packages = {x.name for x in importlib.metadata.distributions()}
        filtered_requirements = []
        try:
            with open(req_file, "r") as read_file:
                requirements = read_file.readlines()

            log.info(f"Installing requirements for plugin {self.id}")
            for req in requirements:
                req = req.strip()
                if not req or req.startswith('#'):
                    continue

                # get package name
                package_name = Requirement(req).name

                # check if package is installed
                if package_name not in installed_packages:
                    filtered_requirements.append(req)
                    continue
        except Exception as e:
            log.error(f"Error during requirements check: {e}, for {self.id}")

        if len(filtered_requirements) == 0:
            return

        # Use delete=False and close the file before subprocess reads it
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as tmp:
            tmp.write("\n".join(filtered_requirements))
            tmp_name = tmp.name

        try:
            subprocess.run(
                ["uv", "pip", "install", "--no-cache", "-r", tmp_name],
                check=True
            )
        except subprocess.CalledProcessError as e:
            log.error(f"Error while installing plugin {self.id} requirements: {e}")

            # Uninstall the previously installed packages
            log.info(f"Uninstalling requirements for: {self.id}")
            subprocess.run(["uv", "pip", "uninstall", "-r", tmp_name], check=True)

            raise Exception(f"Error during plugin {self.id} requirements installation")
        finally:
            # Clean up the temporary file
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

            # Clean __pycache__ directories (cross-platform approach)
            for pycache in Path("/app").rglob("__pycache__"):
                shutil.rmtree(pycache, ignore_errors=True)

    # lists of hooks and tools
    def _load_decorated_functions(self):
        hooks = []
        procedures = []
        endpoints = []
        plugin_overrides = []

        load_done = True
        for py_file in self._py_files:
            py_filename = self._get_py_filename_dotted_notation(py_file)

            log.debug(f"Import module {py_filename}")

            # save a reference to decorated functions
            try:
                plugin_module = importlib.import_module(py_filename)
                importlib.reload(plugin_module)

                hooks += getmembers(plugin_module, lambda obj: isinstance(obj, CatHook))
                procedures += (
                        getmembers(plugin_module, lambda obj: isinstance(obj, CatTool)) +
                        getmembers(plugin_module, lambda obj: isinstance(obj, CatForm) and not isabstract(obj) and obj.autopilot) +
                        getmembers(plugin_module, lambda obj: isinstance(obj, CatMcpClient) and not isabstract(obj))
                )
                endpoints += getmembers(plugin_module, lambda obj: isinstance(obj, CatEndpoint))
                plugin_overrides += getmembers(plugin_module, lambda obj: isinstance(obj, CatPluginDecorator))
            except Exception as e:
                log.error(
                    f"Error in {py_filename}: {str(e)}. Unable to load plugin {self._id}"
                )
                log.warning(self.plugin_specific_error_message())
                load_done = False
                break

        if not load_done:
            self._unload_decorated_functions()
            raise Exception(f"Error loading plugin {self._id}")

        # clean and enrich instances
        self._hooks = list(map(self._clean_hook, hooks))
        self._procedures = list(map(self._clean_procedure, procedures))
        self._endpoints = list(map(self._clean_endpoint, endpoints))

        self._plugin_overrides = {override.name: override for _, override in plugin_overrides}

    def _unload_decorated_functions(self):
        self._hooks = []
        self._procedures = []
        self._endpoints = []
        self._plugin_overrides = {}

    def plugin_specific_error_message(self):
        name = self.manifest.name
        url = self.manifest.plugin_url
        if url:
            return f"To resolve any problem related to {name} plugin, contact the creator using github issue at the link {url}"
        return f"Error in {name} plugin, contact the creator"

    def _clean_hook(self, hook: Tuple[str, CatHook]):
        # getmembers returns a tuple
        _, h = hook
        h.plugin_id = self._id
        return h

    def _clean_procedure(self, procedure: Tuple[str, CatProcedure]):
        # getmembers returns a tuple
        _, p = procedure
        p.plugin_id = self._id
        return p

    def _clean_endpoint(self, endpoint: Tuple[str, CatEndpoint]):
        # getmembers returns a tuple
        _, e = endpoint
        e.plugin_id = self._id
        return e

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
    def procedures(self):
        return self._procedures

    @property
    def tools(self):
        return [p for p in self._procedures if isinstance(p, CatTool)]

    @property
    def forms(self):
        return [p for p in self._procedures if isinstance(p, CatForm)]

    @property
    def mcp_clients(self):
        return [p for p in self._procedures if isinstance(p, CatMcpClient)]

    @property
    def endpoints(self):
        return self._endpoints

    @property
    def overrides(self):
        return self._plugin_overrides
