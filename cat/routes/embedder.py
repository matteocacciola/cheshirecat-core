from typing import Dict
from fastapi import APIRouter, Body, BackgroundTasks

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse
from cat.services.service_factory import ServiceFactory


router = APIRouter(tags=["Embedder"], prefix="/embedder")


# get configured Embedders and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_embedders_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.EMBEDDER, AuthPermission.READ),
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
    background_tasks: BackgroundTasks,
    embedder_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    info: AuthorizedInfo = check_permissions(AuthResource.EMBEDDER, AuthPermission.WRITE),
) -> UpsertSettingResponse:
    """Upsert the Embedder setting"""
    lizard = info.lizard
    previous_embedder_name = lizard.embedder_name
    previous_embedder_size = lizard.embedder_size

    result = ServiceFactory(
        lizard.plugin_manager,
        factory_allowed_handler_name="factory_allowed_embedders",
        setting_category="embedder",
        schema_name="languageEmbedderName",
    ).upsert_service(lizard.agent_key, embedder_name, payload)

    current_embedder_name = lizard.embedder_name
    current_embedder_size = lizard.embedder_size

    # if there is nothing to update, then just return the response
    if previous_embedder_name == current_embedder_name and previous_embedder_size == current_embedder_size:
        return UpsertSettingResponse(**result)

    # otherwise, inform the Cheshire Cats about the new embedder available in the system
    background_tasks.add_task(info.lizard.embed_all_in_cheshire_cats)

    return UpsertSettingResponse(**result)
