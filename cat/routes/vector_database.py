from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse
from cat.services.service_factory import ServiceFactory

router = APIRouter(tags=["Vector Database"], prefix="/vector_database")


# get configured LLMs and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse, summary="Get Vector Databases Settings")
async def get_vector_databases_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.VECTOR_DATABASE, AuthPermission.READ),
) -> GetSettingsResponse:
    """Get the list of the Vector Databases settings and their configuration schemas"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_vector_databases",
        setting_category="vector_database",
        schema_name="vectorDatabaseName",
    ).get_factory_settings(ccat.id)


@router.get(
    "/settings/{vector_database_name}", response_model=GetSettingResponse, summary="Get Vector Database Settings"
)
async def get_vector_database_settings(
    vector_database_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.VECTOR_DATABASE, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified Vector Database"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_vector_databases",
        setting_category="vector_database",
        schema_name="vectorDatabaseName",
    ).get_factory_setting(ccat.id, vector_database_name)


@router.put(
    "/settings/{vector_database_name}", response_model=UpsertSettingResponse, summary="Upsert Vector Database Settings"
)
async def upsert_vector_database_setting(
    vector_database_name: str,
    payload: Dict = Body(...),
    info: AuthorizedInfo = check_permissions(AuthResource.VECTOR_DATABASE, AuthPermission.WRITE),
) -> UpsertSettingResponse:
    """Upsert the Vector Database setting"""
    ccat = info.cheshire_cat

    result = ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_vector_databases",
        setting_category="vector_database",
        schema_name="vectorDatabaseName",
    ).upsert_service(ccat.agent_key, vector_database_name, payload)
    return UpsertSettingResponse(**result)
