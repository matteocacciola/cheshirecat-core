from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.permissions import AdminAuthResource, AuthPermission, check_admin_permissions
from cat.factory.embedder import EmbedderFactory
from cat.looking_glass import BillTheLizard
from cat.routes.routes_utils import (
    GetSettingsResponse,
    GetSettingResponse,
    UpsertSettingResponse,
    get_factory_settings,
    get_factory_setting,
    on_upsert_factory_setting,
)

router = APIRouter()


# get configured Embedders and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_embedders_settings(
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.EMBEDDER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the Embedders"""
    return get_factory_settings(lizard.config_key, EmbedderFactory(lizard.plugin_manager))


@router.get("/settings/{embedder_name}", response_model=GetSettingResponse)
async def get_embedder_settings(
    embedder_name: str,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.EMBEDDER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Embedder"""
    return get_factory_setting(lizard.config_key, embedder_name, EmbedderFactory(lizard.plugin_manager))


@router.put("/settings/{embedder_name}", response_model=UpsertSettingResponse)
async def upsert_embedder_setting(
    embedder_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.EMBEDDER, AuthPermission.EDIT),
) -> UpsertSettingResponse:
    """Upsert the Embedder setting"""
    on_upsert_factory_setting(embedder_name, EmbedderFactory(lizard.plugin_manager))

    response = await lizard.replace_embedder(embedder_name, payload)
    return UpsertSettingResponse(**response.model_dump())
