from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse
from cat.services.service_factory import ServiceFactory


router = APIRouter(tags=["Auth Handler"], prefix="/auth_handler")


@router.get("/settings", response_model=GetSettingsResponse)
async def get_auth_handler_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the AuthHandlers"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_auth_handlers",
        setting_category="auth_handler",
        schema_name="authorizatorName",
    ).get_factory_settings(ccat.agent_key)


@router.get("/settings/{auth_handler_name}", response_model=GetSettingResponse)
async def get_auth_handler_setting(
    auth_handler_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get the settings of a specific AuthHandler"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_auth_handlers",
        setting_category="auth_handler",
        schema_name="authorizatorName",
    ).get_factory_setting(ccat.agent_key, auth_handler_name)


@router.put("/settings/{auth_handler_name}", response_model=UpsertSettingResponse)
async def upsert_authenticator_setting(
    auth_handler_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.LIST),
    payload: Dict = Body(...),
) -> UpsertSettingResponse:
    """Upsert the settings of a specific AuthHandler"""
    ccat = info.cheshire_cat

    result = ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_auth_handlers",
        setting_category="auth_handler",
        schema_name="authorizatorName",
    ).upsert_service(ccat.agent_key, auth_handler_name, payload)
    return UpsertSettingResponse(**result)
