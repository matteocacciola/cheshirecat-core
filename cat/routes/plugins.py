from typing import Dict
from fastapi import Body, APIRouter, Request
from pydantic import ValidationError
from slugify import slugify

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.db.cruds import plugins as crud_plugins
from cat.exceptions import CustomValidationException, CustomNotFoundException
from cat.looking_glass import BillTheLizard
from cat.routes.routes_utils import (
    GetAvailablePluginsResponse,
    GetSettingResponse,
    PluginsSettingsResponse,
    TogglePluginResponse,
    get_available_plugins,
    get_plugins_settings,
    get_plugin_settings,
)

router = APIRouter(tags=["Plugins"], prefix="/plugins")


# GET plugins
@router.get("/", response_model=GetAvailablePluginsResponse)
async def get_cheshirecat_available_plugins(
    query: str = None,
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.LIST),
    # author: str = None, to be activated in case of more granular search
    # tag: str = None, to be activated in case of more granular search
) -> GetAvailablePluginsResponse:
    """List available plugins"""
    if query is not None:
        query = slugify(query, separator="_")

    return await get_available_plugins(info.cheshire_cat.plugin_manager, query)


@router.put("/toggle/{plugin_id}", status_code=200, response_model=TogglePluginResponse)
async def toggle_plugin(
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
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.EDIT),
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
    request: Request,
    plugin_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.PLUGIN, AuthPermission.EDIT),
) -> GetSettingResponse:
    """Resets the settings of a specific plugin"""
    plugin_id = slugify(plugin_id, separator="_")

    # Get the factory settings of the plugin
    lizard: BillTheLizard = request.app.state.lizard
    factory_settings = crud_plugins.get_setting(lizard.config_key, plugin_id)
    if factory_settings is None:
        raise CustomNotFoundException("Plugin not found.")

    # access cat instance
    ccat = info.cheshire_cat

    if not ccat.plugin_manager.local_plugin_exists(plugin_id):
        raise CustomNotFoundException("Plugin not found")

    crud_plugins.set_setting(ccat.id, plugin_id, factory_settings)

    return GetSettingResponse(name=plugin_id, value=factory_settings)
