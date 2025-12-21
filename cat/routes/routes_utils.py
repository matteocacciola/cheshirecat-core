import asyncio
from datetime import datetime, timedelta
import io
import json
import jwt
import mimetypes
from ast import literal_eval
from copy import deepcopy
from typing import Dict, List, Any, Type
import tomli
from fastapi import Query, UploadFile, BackgroundTasks, Request
from langchain_core.caches import InMemoryCache
from langchain_core.globals import set_llm_cache
from pydantic import BaseModel, model_serializer
from fastapi_healthz import HealthCheckStatusEnum, HealthCheckAbstract
from pytz import utc

from cat import utils
from cat.auth.auth_utils import DEFAULT_JWT_ALGORITHM
from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission
from cat.db.cruds import settings as crud_settings
from cat.db.database import DEFAULT_AGENT_KEY
from cat.env import get_env
from cat.exceptions import CustomForbiddenException, CustomValidationException
from cat.factory.base_factory import BaseFactory
from cat.log import log
from cat.looking_glass import BillTheLizard
from cat.looking_glass.mad_hatter.mad_hatter import MadHatter
from cat.looking_glass.mad_hatter.plugin import Plugin
from cat.looking_glass.mad_hatter.plugin_manifest import PluginManifest
from cat.looking_glass.mad_hatter.registry import registry_search_plugins


class Plugins(BaseModel):
    installed: List[PluginManifest]
    registry: List[PluginManifest]


class UserCredentials(BaseModel):
    username: str
    password: str


class JWTResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UpsertSettingResponse(BaseModel):
    name: str
    value: Dict

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        """Custom serializer that will be used by FastAPI"""
        value = self.value.copy()  # Create a copy to avoid modifying the original value
        value = {
            k: "********" if isinstance(v, str) and any(suffix in k for suffix in ["_key", "_secret"]) else v
            for k, v in value.items()
        }

        return {
            "name": self.name,
            "value": value
        }


class GetSettingResponse(UpsertSettingResponse):
    scheme: Dict[str, Any] | None = None

    @model_serializer
    def serialize_model(self) -> Dict[str, Any]:
        """Custom serializer that will be used by FastAPI"""
        serialized = super().serialize_model()
        serialized["scheme"] = self.scheme
        return serialized


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


async def auth_token(credentials: UserCredentials, agent_id: str):
    """
    Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """
    # use username and password to authenticate user from local identity provider and get token
    from cat.db.cruds import users as crud_users

    key_id = agent_id

    # brutal search over users, which are stored in a simple dictionary.
    # waiting to have graph in core to store them properly
    user = crud_users.get_user_by_credentials(key_id, credentials.username, credentials.password)
    if not user:
        # Invalid username or password
        # wait a little to avoid brute force attacks
        await asyncio.sleep(1)
        raise CustomForbiddenException("Invalid Credentials")

    # using seconds for easier testing
    expire_delta_in_seconds = float(get_env("CCAT_JWT_EXPIRE_MINUTES")) * 60
    expires = datetime.now(utc) + timedelta(seconds=expire_delta_in_seconds)

    jwt_content = {
        "sub": user["id"],  # Subject (the user ID)
        "username": credentials.username,  # Username
        "permissions": user["permissions"],  # User permissions
        "exp": expires  # Expiry date as a Unix timestamp
    }
    access_token = jwt.encode(jwt_content, get_env("CCAT_JWT_SECRET"), algorithm=DEFAULT_JWT_ALGORITHM)
    return JWTResponse(access_token=access_token)


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
    bill_the_lizard.fastapi_app = app

    await bill_the_lizard.create_cheshire_cat(DEFAULT_AGENT_KEY)

    # load the Manager and the Job Handler
    app.state.lizard = bill_the_lizard


async def shutdown_app(app):
    utils.singleton.instances.clear()

    # shutdown Manager
    await app.state.lizard.shutdown()
    del app.state.lizard


def get_factory_settings(agent_id: str, factory: BaseFactory) -> GetSettingsResponse:
    saved_settings = crud_settings.get_settings_by_category(agent_id, factory.setting_category)

    settings = [GetSettingResponse(
        name=class_name,
        value=saved_settings["value"] if class_name == saved_settings["name"] else {},
        scheme=scheme
    ) for class_name, scheme in factory.get_schemas().items()]

    return GetSettingsResponse(settings=settings, selected_configuration=saved_settings["name"])


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


def on_upload_single_file(
    request: Request,
    info: AuthorizedInfo,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    metadata: str | None = None,
):
    from cat.looking_glass import BillTheLizard

    lizard: BillTheLizard = request.app.state.lizard
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