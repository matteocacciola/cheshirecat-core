import mimetypes
from typing import Dict
import aiofiles
from fastapi import Body, APIRouter, UploadFile
from pydantic import ValidationError
from slugify import slugify

from cat.log import log
from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.db.cruds import plugins as crud_plugins
from cat.exceptions import CustomValidationException, CustomNotFoundException
from cat.routes.routes_utils import (
    GetAvailablePluginsResponse,
    GetSettingResponse,
    PluginsSettingsResponse,
    TogglePluginResponse,
    get_available_plugins,
    get_plugins_settings,
    get_plugin_settings,
    InstallPluginResponse,
    GetPluginDetailsResponse,
    DeletePluginResponse,
    InstallPluginFromRegistryResponse,
    create_plugin_manifest
)
from cat.utils import get_allowed_plugins_mime_types

router = APIRouter(tags=["Plugins"], prefix="/plugins")


# GET plugins
@router.get("/", response_model=GetAvailablePluginsResponse)
async def get_cheshirecat_available_plugins(
    query: str = None,
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.READ),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""
    if query is not None:
        query = slugify(query, separator="_")

    return await get_available_plugins(info.lizard.plugin_registry, info.cheshire_cat.plugin_manager, query)


@router.put("/toggle/{plugin_id}", response_model=TogglePluginResponse)
async def toggle_plugin_cheshirecat(
    plugin_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.WRITE),
) -> TogglePluginResponse:
    """Enable or disable a single plugin"""
    plugin_id = slugify(plugin_id, separator="_")

    # access cat instance
    ccat = info.cheshire_cat

    # check if plugin exists
    if not ccat.plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # toggle plugin
    ccat.plugin_manager.toggle_plugin(plugin_id)
    return TogglePluginResponse(info=f"Plugin {plugin_id} toggled")


@router.get("/settings", response_model=PluginsSettingsResponse)
async def get_cheshirecat_plugins_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.READ),
) -> PluginsSettingsResponse:
    """Returns the settings of all the plugins"""
    ccat = info.cheshire_cat
    return get_plugins_settings(ccat.plugin_manager, ccat.id)


@router.get("/settings/{plugin_id}", response_model=GetSettingResponse)
async def get_cheshirecat_plugin_settings(
    plugin_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.READ),
) -> GetSettingResponse:
    """Returns the settings of a specific plugin"""
    plugin_id = slugify(plugin_id, separator="_")

    ccat = info.cheshire_cat
    plugin_manager = ccat.plugin_manager
    if not plugin_manager.local_plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    return get_plugin_settings(plugin_manager, plugin_id, ccat.id)


@router.put("/settings/{plugin_id}", response_model=GetSettingResponse)
async def upsert_cheshirecat_plugin_settings(
    plugin_id: str,
    payload: Dict = Body({"setting_a": "some value", "setting_b": "another value"}),
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.WRITE),
) -> GetSettingResponse:
    """Updates the settings of a specific plugin"""
    plugin_id = slugify(plugin_id, separator="_")

    # access cat instance
    ccat = info.cheshire_cat

    if not ccat.plugin_manager.local_plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # Get the plugin object
    plugin = ccat.plugin_manager.plugins[plugin_id]

    try:
        # Load the plugin settings Pydantic model, and validate the settings
        plugin.settings_model().model_validate(payload)
    except ValidationError as e:
        raise CustomValidationException("\n".join(list(map(lambda x: x["msg"], e.errors()))))

    final_settings = plugin.save_settings(payload, ccat.id)

    return GetSettingResponse(name=plugin_id, value=final_settings)


@router.post("/settings/{plugin_id}", response_model=GetSettingResponse)
async def reset_cheshirecat_plugin_settings(
    plugin_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.WRITE),
) -> GetSettingResponse:
    """Resets the settings of a specific plugin"""
    plugin_id = slugify(plugin_id, separator="_")

    # Get the factory settings of the plugin
    factory_settings = crud_plugins.get_setting(info.lizard.config_key, plugin_id)
    if factory_settings is None:
        raise CustomNotFoundException("Plugin not found.")

    # access cat instance
    ccat = info.cheshire_cat

    if not ccat.plugin_manager.local_plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    crud_plugins.set_setting(ccat.id, plugin_id, factory_settings)

    return GetSettingResponse(name=plugin_id, value=factory_settings)


@router.get("/installed", response_model=GetAvailablePluginsResponse)
async def get_lizard_available_plugins(
    query: str = None,
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.READ),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""
    if query is not None:
        query = slugify(query, separator="_")

    return await get_available_plugins(info.lizard.plugin_registry, info.lizard.plugin_manager, query)


@router.post("/install/upload", response_model=InstallPluginResponse)
async def install_plugin(
    file: UploadFile,
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.WRITE),
) -> InstallPluginResponse:
    """Install a new plugin from a zip file"""
    allowed_mime_types = get_allowed_plugins_mime_types()

    content_type, _ = mimetypes.guess_type(file.filename)
    if content_type not in allowed_mime_types:
        raise CustomValidationException(
            f'MIME type `{file.content_type}` not supported. Admitted types: {", ".join(allowed_mime_types)}'
        )

    log.info(f"Uploading {content_type} plugin {file.filename}")
    plugin_archive_path = f"/tmp/{file.filename}"
    async with aiofiles.open(plugin_archive_path, "wb+") as f:
        content = await file.read()
        await f.write(content)

    try:
        info.lizard.plugin_manager.install_plugin(plugin_archive_path)
    except Exception as e:
        raise CustomValidationException(f"Could not install plugin from file: {e}")

    return InstallPluginResponse(
        filename=file.filename,
        content_type=file.content_type,
        info="Plugin is being installed asynchronously",
    )


@router.post("/install/registry", response_model=InstallPluginFromRegistryResponse)
async def install_plugin_from_registry(
    payload: Dict = Body({"url": "https://github.com/plugin-dev-account/plugin-repo"}),
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.WRITE),
) -> InstallPluginFromRegistryResponse:
    """Install a new plugin from registry"""
    # download zip from registry
    try:
        tmp_plugin_path = await info.lizard.plugin_registry.download_plugin(payload["url"])
        info.lizard.plugin_manager.install_plugin(tmp_plugin_path)
    except Exception as e:
        raise CustomValidationException(f"Could not install plugin from registry: {e}")

    return InstallPluginFromRegistryResponse(url=payload["url"], info="Plugin is being installed asynchronously")


@router.get("/system/settings", response_model=PluginsSettingsResponse)
async def get_lizard_plugins_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.READ),
) -> PluginsSettingsResponse:
    """Returns the default settings of all the plugins"""
    lizard = info.lizard
    return get_plugins_settings(lizard.plugin_manager, lizard.config_key)


@router.get("/system/settings/{plugin_id}", response_model=GetSettingResponse)
async def get_lizard_plugin_settings(
    plugin_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.READ),
) -> GetSettingResponse:
    """Returns the default settings of a specific plugin"""
    lizard = info.lizard
    plugin_manager = lizard.plugin_manager
    if not plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    return get_plugin_settings(plugin_manager, plugin_id, lizard.config_key)


@router.get("/system/details/{plugin_id}", response_model=GetPluginDetailsResponse)
async def get_lizard_plugin_details(
    plugin_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.READ),
) -> GetPluginDetailsResponse:
    """Returns information on a single plugin, at a system level"""
    plugin_manager = info.lizard.plugin_manager
    plugin_id = slugify(plugin_id, separator="_")

    if not plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    active_plugins = plugin_manager.load_active_plugins_ids_from_db()
    plugin = plugin_manager.plugins[plugin_id]

    # get manifest and active True/False. We make a copy to avoid modifying the original obj
    return GetPluginDetailsResponse(data=create_plugin_manifest(plugin, active_plugins))


@router.delete("/uninstall/{plugin_id}", response_model=DeletePluginResponse)
async def uninstall_plugin(
    plugin_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.DELETE),
) -> DeletePluginResponse:
    """Physically remove plugin at a system level."""
    plugin_manager = info.lizard.plugin_manager
    plugin_id = slugify(plugin_id, separator="_")

    if not plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # remove folder, hooks and tools
    plugin_manager.uninstall_plugin(plugin_id)

    return DeletePluginResponse(deleted=plugin_id)


@router.put("/system/toggle/{plugin_id}", response_model=TogglePluginResponse)
async def toggle_plugin_admin(
    plugin_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.SYSTEM, AuthPermission.DELETE),
) -> TogglePluginResponse:
    """Enable or disable a single plugin"""
    plugin_manager = info.lizard.plugin_manager
    plugin_id = slugify(plugin_id, separator="_")

    # check if plugin exists
    if not plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # toggle plugin
    plugin_manager.toggle_plugin(plugin_id)
    return TogglePluginResponse(info=f"Plugin {plugin_id} toggled")
