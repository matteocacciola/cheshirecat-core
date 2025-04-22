from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.factory.auth_handler import AuthHandlerFactory
from cat.factory.base_factory import ReplacedNLPConfig
from cat.routes.routes_utils import (
    GetSettingsResponse,
    GetSettingResponse,
    UpsertSettingResponse,
    get_factory_settings,
    get_factory_setting,
    on_upsert_factory_setting,
)

router = APIRouter()


@router.get("/settings", response_model=GetSettingsResponse)
async def get_auth_handler_settings(
    cats: ContextualCats = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the AuthHandlers"""

    ccat = cats.cheshire_cat
    return get_factory_settings(ccat.id, AuthHandlerFactory(ccat.plugin_manager))


@router.get("/settings/{auth_handler_name}", response_model=GetSettingResponse)
async def get_auth_handler_setting(
    auth_handler_name: str,
    cats: ContextualCats = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get the settings of a specific AuthHandler"""

    ccat = cats.cheshire_cat
    return get_factory_setting(ccat.id, auth_handler_name, AuthHandlerFactory(ccat.plugin_manager))


@router.put("/settings/{auth_handler_name}", response_model=UpsertSettingResponse)
async def upsert_authenticator_setting(
    auth_handler_name: str,
    cats: ContextualCats = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.LIST),
    payload: Dict = Body(...),
) -> ReplacedNLPConfig:
    """Upsert the settings of a specific AuthHandler"""

    ccat = cats.cheshire_cat
    on_upsert_factory_setting(auth_handler_name, AuthHandlerFactory(ccat.plugin_manager))

    return ccat.replace_auth_handler(auth_handler_name, payload)
