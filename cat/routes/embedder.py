from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cat.factory.embedder import EmbedderFactory
from cat.routes.routes_utils import (
    GetSettingsResponse,
    GetSettingResponse,
    UpsertSettingResponse,
    get_factory_settings,
    get_factory_setting,
    on_upsert_factory_setting,
)

router = APIRouter(tags=["Embedder"], prefix="/embedder")


# get configured Embedders and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_embedders_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.EMBEDDER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the Embedders"""
    lizard = info.lizard
    return get_factory_settings(lizard.config_key, EmbedderFactory(lizard.plugin_manager))


@router.get("/settings/{embedder_name}", response_model=GetSettingResponse)
async def get_embedder_settings(
    embedder_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.EMBEDDER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Embedder"""
    lizard = info.lizard
    return get_factory_setting(lizard.config_key, embedder_name, EmbedderFactory(lizard.plugin_manager))


@router.put("/settings/{embedder_name}", response_model=UpsertSettingResponse)
async def upsert_embedder_setting(
    embedder_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    info: AuthorizedInfo = check_permissions(AuthResource.EMBEDDER, AuthPermission.EDIT),
) -> UpsertSettingResponse:
    """Upsert the Embedder setting"""
    lizard = info.lizard
    on_upsert_factory_setting(embedder_name, EmbedderFactory(lizard.plugin_manager))

    response = await lizard.replace_embedder(embedder_name, payload)
    return UpsertSettingResponse(**response)
