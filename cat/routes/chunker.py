from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse
from cat.services.service_factory import ServiceFactory

router = APIRouter(tags=["Chunking"], prefix="/chunking")


@router.get("/settings", response_model=GetSettingsResponse)
async def get_chunker_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.CHUNKER, AuthPermission.READ),
) -> GetSettingsResponse:
    """Get the list of the Chunkers"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        agent_key=ccat.agent_key,
        hook_manager=ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_chunkers",
        setting_category="chunker",
        schema_name="chunkerName",
    ).get_factory_settings()


@router.get("/settings/{chunker_name}", response_model=GetSettingResponse)
async def get_chunker_setting(
    chunker_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get the settings of a specific Chunker"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        agent_key=ccat.agent_key,
        hook_manager=ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_chunkers",
        setting_category="chunker",
        schema_name="chunkerName",
    ).get_factory_setting(chunker_name)


@router.put("/settings/{chunker_name}", response_model=UpsertSettingResponse)
async def upsert_chunker_setting(
    chunker_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.WRITE),
    payload: Dict = Body(default={}),
) -> UpsertSettingResponse:
    """Upsert the settings of a specific Chunker"""
    ccat = info.cheshire_cat

    result = ServiceFactory(
        agent_key=ccat.agent_key,
        hook_manager=ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_chunkers",
        setting_category="chunker",
        schema_name="chunkerName",
    ).upsert_service(chunker_name, payload)
    return UpsertSettingResponse(**result)
