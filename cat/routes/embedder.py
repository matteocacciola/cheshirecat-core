from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cat.db import crud
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse
from cat.services.service_factory import ServiceFactory


router = APIRouter(tags=["Embedder"], prefix="/embedder")


# get configured Embedders and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_embedders_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.EMBEDDER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the Embedders"""
    lizard = info.lizard
    return ServiceFactory(
        lizard.plugin_manager,
        factory_allowed_handler_name="factory_allowed_embedders",
        setting_category="embedder",
        schema_name="languageEmbedderName",
    ).get_factory_settings(lizard.config_key)


@router.get("/settings/{embedder_name}", response_model=GetSettingResponse)
async def get_embedder_settings(
    embedder_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.EMBEDDER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Embedder"""
    lizard = info.lizard
    return ServiceFactory(
        lizard.plugin_manager,
        factory_allowed_handler_name="factory_allowed_embedders",
        setting_category="embedder",
        schema_name="languageEmbedderName",
    ).get_factory_setting(lizard.config_key, embedder_name)


@router.put("/settings/{embedder_name}", response_model=UpsertSettingResponse)
async def upsert_embedder_setting(
    embedder_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    info: AuthorizedInfo = check_permissions(AuthResource.EMBEDDER, AuthPermission.EDIT),
) -> UpsertSettingResponse:
    """Upsert the Embedder setting"""
    lizard = info.lizard

    result = ServiceFactory(
        lizard.plugin_manager,
        factory_allowed_handler_name="factory_allowed_embedders",
        setting_category="embedder",
        schema_name="languageEmbedderName",
    ).upsert_service(lizard.agent_key, embedder_name, payload)

    # inform the Cheshire Cats about the new embedder available in the system
    for ccat_id in crud.get_agents_main_keys():
        ccat = lizard.get_cheshire_cat(ccat_id)
        if ccat is None:
            continue
        await ccat.vector_memory_handler.initialize(embedder_name, lizard.embedder_size)

    return UpsertSettingResponse(**result)
