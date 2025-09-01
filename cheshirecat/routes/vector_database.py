from typing import Dict
from fastapi import APIRouter, Body

from cheshirecat.auth.connection import AuthorizedInfo
from cheshirecat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cheshirecat.factory.vector_db import VectorDatabaseFactory
from cheshirecat.routes.routes_utils import (
    GetSettingsResponse,
    GetSettingResponse,
    UpsertSettingResponse,
    get_factory_settings,
    get_factory_setting,
    on_upsert_factory_setting,
)

router = APIRouter()


# get configured LLMs and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse, summary="Get Vector Databases Settings")
async def get_vector_databases_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.VECTOR_DATABASE, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the Vector Databases settings and their configuration schemas"""
    ccat = info.cheshire_cat
    return get_factory_settings(ccat.id, VectorDatabaseFactory(ccat.plugin_manager))


@router.get(
    "/settings/{vector_database_name}", response_model=GetSettingResponse, summary="Get Vector Database Settings"
)
async def get_vector_database_settings(
    vector_database_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.VECTOR_DATABASE, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Vector Database"""
    ccat = info.cheshire_cat
    return get_factory_setting(ccat.id, vector_database_name, VectorDatabaseFactory(ccat.plugin_manager))


@router.put(
    "/settings/{vector_database_name}", response_model=UpsertSettingResponse, summary="Upsert Vector Database Settings"
)
async def upsert_vector_database_setting(
    vector_database_name: str,
    payload: Dict = Body(...),
    info: AuthorizedInfo = check_permissions(AuthResource.VECTOR_DATABASE, AuthPermission.EDIT),
) -> UpsertSettingResponse:
    """Upsert the Vector Database setting"""
    ccat = info.cheshire_cat
    on_upsert_factory_setting(vector_database_name, VectorDatabaseFactory(ccat.plugin_manager))

    res = await ccat.replace_vector_memory_handler(vector_database_name, payload)
    return UpsertSettingResponse(**res.model_dump())
