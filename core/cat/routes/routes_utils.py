import asyncio
from ast import literal_eval
import time
from copy import deepcopy
from typing import Dict, List, Any
from fastapi import Query, UploadFile
from pydantic import BaseModel, Field
import io

from cat import utils
from cat.auth.auth_utils import issue_jwt
from cat.auth.connection import AuthorizedInfo
from cat.db.database import DEFAULT_AGENT_KEY
from cat.db.cruds import settings as crud_settings
from cat.exceptions import CustomForbiddenException, CustomValidationException, CustomNotFoundException
from cat.factory.base_factory import ReplacedNLPConfig, BaseFactory
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.plugin import Plugin
from cat.mad_hatter.registry import registry_search_plugins
from cat.memory.utils import VectorMemoryCollectionTypes
from cat.memory.vector_memory import VectorMemory
from cat.memory.vector_memory_builder import VectorMemoryBuilder


class Plugins(BaseModel):
    installed: List[Dict]
    registry: List[Dict]


class UserCredentials(BaseModel):
    username: str
    password: str


class JWTResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UpsertSettingResponse(ReplacedNLPConfig):
    pass


class GetSettingResponse(UpsertSettingResponse):
    scheme: Dict[str, Any] | None = None


class GetSettingsResponse(BaseModel):
    settings: List[GetSettingResponse]
    selected_configuration: str | None


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
    data: Dict


class DeletePluginResponse(BaseModel):
    deleted: str


class MemoryPointBase(BaseModel):
    content: str
    metadata: Dict = Field(default_factory=dict)


# TODO V2: annotate all endpoints and align internal usage (no qdrant PointStruct, no langchain Document)
class MemoryPoint(MemoryPointBase):
    id: str
    vector: List[float]


async def auth_token(credentials: UserCredentials, agent_id: str):
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """

    # use username and password to authenticate user from local identity provider and get token
    access_token = issue_jwt(credentials.username, credentials.password, key_id=agent_id)

    if access_token:
        return JWTResponse(access_token=access_token)

    # Invalid username or password
    # wait a little to avoid brute force attacks
    await asyncio.sleep(1)
    raise CustomForbiddenException("Invalid Credentials")


async def get_plugins(plugin_manager: MadHatter, query: str | None = None) -> Plugins:
    """
    Get the plugins related to the passed plugin manager instance and the query.
    Args:
        plugin_manager: the instance of MadHatter
        query: the query to look for

    Returns:
        The list of plugins
    """

    def create_manifest(plugin: Plugin) -> Dict[str, Any]:
        # get manifest
        manifest = deepcopy(plugin.manifest)  # we make a copy to avoid modifying the plugin obj
        manifest["active"] = (plugin.id in active_plugins)  # pass along if plugin is active or not
        manifest["upgrade"] = None
        manifest["hooks"] = [{"name": hook.name, "priority": hook.priority} for hook in plugin.hooks]
        manifest["tools"] = [{"name": tool.name} for tool in plugin.tools]
        manifest["forms"] = [{"name": form.name} for form in plugin.forms]
        manifest["endpoints"] = [{"name": endpoint.name, "tags": endpoint.tags} for endpoint in plugin.endpoints]
        # do not show already installed plugins among registry plugins
        r = registry_plugins_index.pop(manifest["plugin_url"], None)
        # filter by query
        plugin_text = [str(field) for field in manifest.values()]
        plugin_text = " ".join(plugin_text).lower()
        if (
                (query is None or query.lower() in plugin_text)
                and r is not None
                and r.get("version") is not None
                and r.get("version") != plugin.manifest.get("version")
        ):
            manifest["upgrade"] = r["version"]
        return manifest

    # retrieve plugins from official repo
    registry_plugins = await registry_search_plugins(query)
    # index registry plugins by url
    registry_plugins_index = {p.get("plugin_url"): p for p in registry_plugins if p.get("plugin_url") is not None}

    # get active plugins
    active_plugins = plugin_manager.load_active_plugins_from_db()

    # list installed plugins' manifest
    installed_plugins = [create_manifest(p) for p in plugin_manager.plugins.values()]

    return Plugins(installed=installed_plugins, registry=list(registry_plugins_index.values()))


async def get_available_plugins(
    plugin_manager: MadHatter,
    query: str = None,
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""

    plugins = await get_plugins(plugin_manager, query)

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

    if not plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    settings = plugin_manager.plugins[plugin_id].load_settings(agent_id)
    scheme = plugin_manager.plugins[plugin_id].settings_schema()

    if scheme["properties"] == {}:
        scheme = {}

    return GetSettingResponse(name=plugin_id, value=settings, scheme=scheme)


def memory_collection_is_accessible(collection_id: str) -> None:
    # check if collection exists
    if collection_id not in VectorMemoryCollectionTypes:
        raise CustomNotFoundException("Collection does not exist.")

    # do not touch procedural memory
    if collection_id == VectorMemoryCollectionTypes.PROCEDURAL:
        raise CustomValidationException("Procedural memory is read-only.")


async def verify_memory_point_existence(collection_id: str, point_id: str, vector_memory: VectorMemory) -> None:
    memory_collection_is_accessible(collection_id)

    # check if point exists
    points = await vector_memory.collections[collection_id].retrieve_points([point_id])
    if not points:
        raise CustomNotFoundException("Point does not exist.")


async def upsert_memory_point(
    collection_id: str, point: MemoryPointBase, info: AuthorizedInfo, point_id: str = None
) -> MemoryPoint:
    ccat = info.cheshire_cat
    vector_memory = ccat.memory.vectors

    # embed content
    embedding = ccat.embedder.embed_query(point.content)

    # ensure source is set
    if not point.metadata.get("source"):
        point.metadata["source"] = info.user.id  # this will do also for declarative memory

    # ensure when is set
    if not point.metadata.get("when"):
        point.metadata["when"] = time.time()  # if when is not in the metadata set the current time

    # create point
    qdrant_point = await vector_memory.collections[collection_id].add_point(
        content=point.content,
        vector=embedding,
        metadata=point.metadata,
        id=point_id,
    )

    return MemoryPoint(
        metadata=qdrant_point.payload["metadata"],
        content=qdrant_point.payload["page_content"],
        vector=qdrant_point.vector,
        id=qdrant_point.id
    )


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
    # load the Manager and the Job Handler
    app.state.lizard = BillTheLizard().set_fastapi_app(app)
    app.state.white_rabbit = WhiteRabbit()

    memory_builder = VectorMemoryBuilder()
    await memory_builder.build()
    await app.state.lizard.create_cheshire_cat(DEFAULT_AGENT_KEY)


async def shutdown_app(app):
    utils.singleton.instances.clear()

    # shutdown Manager
    app.state.white_rabbit.shutdown()
    await app.state.lizard.shutdown()

    del app.state.lizard
    del app.state.white_rabbit


def get_factory_settings(agent_id: str, factory: BaseFactory) -> GetSettingsResponse:
    # get selected AuthHandler
    selected = crud_settings.get_setting_by_name(agent_id, factory.setting_name)
    if selected is not None:
        selected = selected["value"]["name"]

    saved_settings = crud_settings.get_settings_by_category(agent_id, factory.setting_factory_category)
    saved_settings = {s["name"]: s for s in saved_settings}

    settings = [GetSettingResponse(
        name=class_name,
        value=saved_settings[class_name]["value"] if class_name in saved_settings else {},
        scheme=scheme
    ) for class_name, scheme in factory.get_schemas().items()]

    return GetSettingsResponse(settings=settings, selected_configuration=selected)


def get_factory_setting(agent_id: str, configuration_name: str, factory: BaseFactory) -> GetSettingResponse:
    schemas = factory.get_schemas()

    allowed_configurations = list(schemas.keys())
    if configuration_name not in allowed_configurations:
        raise CustomValidationException(f"{configuration_name} not supported. Must be one of {allowed_configurations}")

    setting = crud_settings.get_setting_by_name(agent_id, configuration_name)
    setting = {} if setting is None else setting["value"]

    scheme = schemas[configuration_name]

    return GetSettingResponse(name=configuration_name, value=setting, scheme=scheme)


def on_upsert_factory_setting(configuration_name: str, factory: BaseFactory):
    schemas = factory.get_schemas()

    allowed_configurations = list(schemas.keys())
    if configuration_name not in allowed_configurations:
        raise CustomValidationException(f"{configuration_name} not supported. Must be one of {allowed_configurations}")
