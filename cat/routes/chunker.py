from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.factory.chunker import ChunkerFactory
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
async def get_chunker_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.CHUNKER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the Chunkers"""
    ccat = info.cheshire_cat
    return get_factory_settings(ccat.id, ChunkerFactory(ccat.plugin_manager))


@router.get("/settings/{chunker_name}", response_model=GetSettingResponse)
async def get_chunker_setting(
    chunker_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get the settings of a specific Chunker"""
    ccat = info.cheshire_cat
    return get_factory_setting(ccat.id, chunker_name, ChunkerFactory(ccat.plugin_manager))


@router.put("/settings/{chunker_name}", response_model=UpsertSettingResponse)
async def upsert_chunker_setting(
    chunker_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.AUTH_HANDLER, AuthPermission.LIST),
    payload: Dict = Body(...),
) -> UpsertSettingResponse:
    """Upsert the settings of a specific Chunker"""
    ccat = info.cheshire_cat
    on_upsert_factory_setting(chunker_name, ChunkerFactory(ccat.plugin_manager))

    return UpsertSettingResponse(**ccat.replace_chunker(chunker_name, payload).model_dump())
