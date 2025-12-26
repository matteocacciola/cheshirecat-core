import io
import json
import mimetypes
from ast import literal_eval
from copy import deepcopy
from typing import Dict, List, Any, Type
import tomli
from fastapi import Query, UploadFile, BackgroundTasks
from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache
from pydantic import BaseModel
from fastapi_healthz import HealthCheckStatusEnum, HealthCheckAbstract

from cat import utils
from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission
from cat.exceptions import CustomValidationException
from cat.log import log
from cat.looking_glass import BillTheLizard
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.looking_glass.mad_hatter.plugin import Plugin
from cat.looking_glass.mad_hatter.plugin_manifest import PluginManifest
from cat.looking_glass.mad_hatter.registry import registry_search_plugins
from cat.services.factory.base_factory import GetSettingResponse


class Plugins(BaseModel):
    installed: List[PluginManifest]
    registry: List[PluginManifest]


class UserCredentials(BaseModel):
    username: str
    password: str


class JWTResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class GetAvailablePluginsFilter(BaseModel):
    query: str | None


class GetAvailablePluginsResponse(Plugins):
    filters: GetAvailablePluginsFilter


class TogglePluginResponse(BaseModel):
    info: str


class InstallPluginResponse(TogglePluginResponse):
    filename: str
    content_type: str


class InstallPluginFromRegistryResponse(TogglePluginResponse):
    url: str


class PluginsSettingsResponse(BaseModel):
    settings: List[GetSettingResponse]


class GetPluginDetailsResponse(BaseModel):
    data: PluginManifest


class DeletePluginResponse(BaseModel):
    deleted: str


class HealthCheckLocal(HealthCheckAbstract):
    @property
    def service(self) -> str:
        return "cheshire-cat"

    @property
    def connection_uri(self) -> str:
        return utils.get_base_url()

    @property
    def tags(self) -> List[str]:
        return ["cheshire-cat", "local"]

    @property
    def comments(self) -> list[str]:
        with open("pyproject.toml", "rb") as f:
            project_toml = tomli.load(f)["project"]
            return [f"version: {project_toml['version']}"]

    def check_health(self) -> HealthCheckStatusEnum:
        return HealthCheckStatusEnum.HEALTHY


def create_plugin_manifest(
    plugin: Plugin,
    active_plugins: List[str],
    registry_plugins_index: Dict[str, PluginManifest] | None = None,
    query: str | None = None
) -> PluginManifest:
    # get manifest
    manifest: PluginManifest = deepcopy(plugin.manifest)  # we make a copy to avoid modifying the plugin obj
    manifest.local_info = {
        "active": (plugin.id in active_plugins),  # pass along if plugin is active or not
        "hooks": [{"name": hook.name, "priority": hook.priority} for hook in plugin.hooks],
        "tools": [{"name": tool.name} for tool in plugin.tools],
        "forms": [{"name": form.name} for form in plugin.forms],
        "mcp_clients": [{"name": mcp_client.name} for mcp_client in plugin.mcp_clients],
        "endpoints": [{"name": endpoint.name, "tags": endpoint.tags} for endpoint in plugin.endpoints],
    }

    if registry_plugins_index is not None:
        manifest.local_info["upgrade"] = None

        # do not show already installed plugins among registry plugins
        r = registry_plugins_index.pop(manifest.plugin_url, None)
        # filter by query
        plugin_text = manifest.model_dump_json()
        if (
                (query is None or query.lower() in plugin_text)
                and r is not None
                and r.version is not None
                and r.version != plugin.manifest.version
        ):
            manifest.local_info["upgrade"] = r.version

    return manifest


async def get_available_plugins(
    plugin_manager: MadHatter,
    query: str = None,
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """
    Get the plugins related to the passed plugin manager instance and the query.
    Args:
        plugin_manager: the instance of MadHatter
        query: the query to look for

    Returns:
        The list of plugins
    """
    # retrieve plugins from official repo
    registry_plugins = await registry_search_plugins(query)
    # index registry plugins by url
    registry_plugins_index = {p.plugin_url: p for p in registry_plugins if p.plugin_url is not None}

    # get active plugins
    active_plugins_ids = plugin_manager.load_active_plugins_ids_from_db()

    # list installed plugins' manifest
    installed_plugins = [
        create_plugin_manifest(p, active_plugins_ids, registry_plugins_index, query)
        for p in plugin_manager.available_plugins.values()
    ]

    plugins = Plugins(installed=installed_plugins, registry=list(registry_plugins_index.values()))

    return GetAvailablePluginsResponse(
        filters=GetAvailablePluginsFilter(
            query=query,
            # "author": author, to be activated in case of more granular search
            # "tag": tag, to be activated in case of more granular search
        ),
        installed=plugins.installed,
        registry=plugins.registry,
    )


def get_plugins_settings(plugin_manager: MadHatter, agent_id: str) -> PluginsSettingsResponse:
    settings = []

    # plugins are managed by the MadHatter class (and its inherits)
    for plugin in plugin_manager.plugins.values():
        try:
            plugin_settings = plugin.load_settings(agent_id)
            plugin_schema = plugin.settings_schema()
            if plugin_schema["properties"] == {}:
                plugin_schema = {}
            settings.append(
                GetSettingResponse(name=plugin.id, value=plugin_settings, scheme=plugin_schema)
            )
        except Exception as e:
            raise CustomValidationException(
                f"Error loading {plugin} settings. The result will not contain the settings for this plugin. "
                f"Error details: {e}"
            )

    return PluginsSettingsResponse(settings=settings)


def get_plugin_settings(plugin_manager: MadHatter, plugin_id: str, agent_id: str) -> GetSettingResponse:
    """Returns the settings of a specific plugin"""
    settings = plugin_manager.plugins[plugin_id].load_settings(agent_id)
    scheme = plugin_manager.plugins[plugin_id].settings_schema()

    if scheme["properties"] == {}:
        scheme = {}

    return GetSettingResponse(name=plugin_id, value=settings, scheme=scheme)


def create_dict_parser(param_name: str, description: str | None = None):
    def parser(
        param_value: str | None = Query(
            default=None,
            alias=param_name,
            description=description or f"{param_name} JSON filter."
        )
    ) -> Dict[str, Any]:
        if not param_value:
            return {}
        try:
            return literal_eval(param_value)
        except ValueError:
            return {}
    return parser


def format_upload_file(upload_file: UploadFile) -> UploadFile:
    file_content = upload_file.file.read()
    return UploadFile(filename=upload_file.filename, file=io.BytesIO(file_content))


async def startup_app(app):
    set_llm_cache(InMemoryCache())
    utils.pod_id()

    bill_the_lizard = BillTheLizard()
    bill_the_lizard.bootstrap_services()
    bill_the_lizard.fastapi_app = app

    # load the Manager and the Job Handler
    app.state.lizard = bill_the_lizard


async def shutdown_app(app):
    utils.singleton.instances.clear()

    # shutdown Manager
    await app.state.lizard.shutdown()
    del app.state.lizard


def on_upload_single_file(
    info: AuthorizedInfo,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    metadata: str | None = None,
):
    lizard = info.lizard
    cat = info.stray_cat or info.cheshire_cat

    # Check the file format is supported
    admitted_types = cat.file_handlers.keys()

    # Get file mime type
    content_type, _ = mimetypes.guess_type(file.filename)
    log.info(f"Uploaded {content_type} down the rabbit hole")

    # check if MIME type of uploaded file is supported
    if content_type not in admitted_types:
        CustomValidationException(
            f'MIME type {content_type} not supported. Admitted types: {" - ".join(admitted_types)}'
        )

    # upload file to long term memory, in the background
    uploaded_file = deepcopy(format_upload_file(file))
    # we deepcopy the file because FastAPI does not keep the file in memory after the response returns to the client
    # https://github.com/tiangolo/fastapi/discussions/10936
    background_tasks.add_task(
        lizard.rabbit_hole.ingest_file,
        cat=cat,
        file=uploaded_file,
        metadata=json.loads(metadata)
    )


def validate_permissions(permissions: Dict[str, List[str]], resources: Type[utils.Enum]):
    if not permissions:
        raise ValueError("Permissions cannot be empty")

    # Check if all permissions are empty
    all_items_empty = all([not p for p in permissions.values()])
    if all_items_empty:
        raise ValueError("At least one permission must be set")

    # Validate each resource and its permissions
    for k_, v_ in permissions.items():
        if k_ not in resources:
            raise ValueError(f"Invalid resource: {k_}")
        if any([p not in AuthPermission for p in v_]):
            raise ValueError(f"Invalid permissions for {k_}")

    return permissions
