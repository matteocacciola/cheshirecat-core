from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.factory.base_factory import ReplacedNLPConfig
from cat.factory.llm import LLMFactory
from cat.routes.routes_utils import (
    GetSettingsResponse,
    GetSettingResponse,
    UpsertSettingResponse,
    get_factory_settings,
    get_factory_setting,
    on_upsert_factory_setting,
)

router = APIRouter()


# get configured LLMs and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse, summary="Get LLMs Settings")
async def get_llms_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.LLM, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the Large Language Models"""

    ccat = info.cheshire_cat
    return get_factory_settings(ccat.id, LLMFactory(ccat.plugin_manager))


@router.get("/settings/{language_model_name}", response_model=GetSettingResponse, summary="Get LLM Settings")
async def get_llm_settings(
    language_model_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.LLM, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Large Language Model"""

    ccat = info.cheshire_cat
    return get_factory_setting(ccat.id, language_model_name, LLMFactory(ccat.plugin_manager))


@router.put("/settings/{language_model_name}", response_model=UpsertSettingResponse, summary="Upsert LLM Settings")
async def upsert_llm_setting(
    language_model_name: str,
    payload: Dict = Body({"openai_api_key": "your-key-here"}),
    info: AuthorizedInfo = check_permissions(AuthResource.LLM, AuthPermission.EDIT),
) -> ReplacedNLPConfig:
    """Upsert the Large Language Model setting"""

    ccat = info.cheshire_cat
    on_upsert_factory_setting(language_model_name, LLMFactory(ccat.plugin_manager))

    return ccat.replace_llm(language_model_name, payload)
