from typing import Dict
from fastapi import Body, APIRouter, UploadFile
from slugify import slugify

from cat.auth.permissions import AuthPermission, AdminAuthResource, check_admin_permissions
from cat.exceptions import CustomValidationException, CustomNotFoundException
from cat.looking_glass import BillTheLizard
from cat.mad_hatter import registry_download_plugin
from cat.routes.routes_utils import (
    DeletePluginResponse,
    GetAvailablePluginsResponse,
    GetPluginDetailsResponse,
    GetSettingResponse,
    InstallPluginFromRegistryResponse,
    InstallPluginResponse,
    PluginsSettingsResponse,
    TogglePluginResponse,
    get_available_plugins,
    get_plugins_settings,
    get_plugin_settings,
    create_plugin_manifest,
)
from cat.utils import get_allowed_plugins_mime_types, load_uploaded_file

router = APIRouter()


# GET plugins
@router.get("/", response_model=GetAvailablePluginsResponse)
async def get_lizard_available_plugins(
    query: str = None,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.LIST),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""
    
    if query is not None:
        query = slugify(query, separator="_")

    return await get_available_plugins(lizard.plugin_manager, query)


@router.post("/upload", response_model=InstallPluginResponse)
async def install_plugin(
    file: UploadFile,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.WRITE),
) -> InstallPluginResponse:
    """Install a new plugin from a zip file"""
    plugin_archive_path = await load_uploaded_file(file, get_allowed_plugins_mime_types())

    try:
        lizard.plugin_manager.install_plugin(plugin_archive_path)
    except Exception as e:
        raise CustomValidationException(f"Could not install plugin from file: {e}")

    return InstallPluginResponse(
        filename=file.filename,
        content_type=file.content_type,
        info="Plugin is being installed asynchronously",
    )


@router.post("/upload/registry", response_model=InstallPluginFromRegistryResponse)
async def install_plugin_from_registry(
    payload: Dict = Body({"url": "https://github.com/plugin-dev-account/plugin-repo"}),
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.WRITE),
) -> InstallPluginFromRegistryResponse:
    """Install a new plugin from registry"""
    # download zip from registry
    try:
        tmp_plugin_path = await registry_download_plugin(payload["url"])
        lizard.plugin_manager.install_plugin(tmp_plugin_path)
    except Exception as e:
        raise CustomValidationException(f"Could not install plugin from registry: {e}")

    return InstallPluginFromRegistryResponse(url=payload["url"], info="Plugin is being installed asynchronously")


@router.get("/settings", response_model=PluginsSettingsResponse)
async def get_lizard_plugins_settings(
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.READ),
) -> PluginsSettingsResponse:
    """Returns the default settings of all the plugins"""
    return get_plugins_settings(lizard.plugin_manager, lizard.config_key)


@router.get("/settings/{plugin_id}", response_model=GetSettingResponse)
async def get_lizard_plugin_settings(
    plugin_id: str,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.READ),
) -> GetSettingResponse:
    """Returns the default settings of a specific plugin"""
    plugin_manager = lizard.plugin_manager
    if not plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    return get_plugin_settings(plugin_manager, plugin_id, lizard.config_key)


@router.get("/{plugin_id}", response_model=GetPluginDetailsResponse)
async def get_plugin_details(
    plugin_id: str,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.READ),
) -> GetPluginDetailsResponse:
    """Returns information on a single plugin, at a system level"""
    plugin_id = slugify(plugin_id, separator="_")

    if not lizard.plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    active_plugins = lizard.plugin_manager.load_active_plugins_ids_from_db()
    plugin = lizard.plugin_manager.plugins[plugin_id]

    # get manifest and active True/False. We make a copy to avoid modifying the original obj
    return GetPluginDetailsResponse(data=create_plugin_manifest(plugin, active_plugins))


@router.delete("/{plugin_id}", response_model=DeletePluginResponse)
async def uninstall_plugin(
    plugin_id: str,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.DELETE),
) -> DeletePluginResponse:
    """Physically remove plugin at a system level."""
    plugin_id = slugify(plugin_id, separator="_")

    if not lizard.plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # remove folder, hooks and tools
    lizard.plugin_manager.uninstall_plugin(plugin_id)

    return DeletePluginResponse(deleted=plugin_id)


@router.put("/toggle/{plugin_id}", status_code=200, response_model=TogglePluginResponse)
async def toggle_plugin(
    plugin_id: str,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.DELETE),
) -> TogglePluginResponse:
    """Enable or disable a single plugin"""
    plugin_id = slugify(plugin_id, separator="_")

    # check if plugin exists
    if not lizard.plugin_manager.plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    # toggle plugin
    lizard.plugin_manager.toggle_plugin(plugin_id)
    return TogglePluginResponse(info=f"Plugin {plugin_id} toggled")
