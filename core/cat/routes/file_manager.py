from typing import Dict
from fastapi import APIRouter, Body

from cat.auth.connection import ContextualCats
from cat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cat.factory.base_factory import ReplacedNLPConfig
from cat.factory.file_manager import FileManagerFactory
from cat.routes.routes_utils import (
    GetSettingsResponse,
    GetSettingResponse,
    UpsertSettingResponse,
    get_factory_settings,
    get_factory_setting,
    on_upsert_factory_setting,
)

router = APIRouter()


# get configured Plugin File Managers and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_file_managers_settings(
    cats: ContextualCats = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the File Managers and their settings"""

    ccat = cats.cheshire_cat
    return get_factory_settings(ccat.id, FileManagerFactory(ccat.plugin_manager))


@router.get("/settings/{file_manager_name}", response_model=GetSettingResponse)
async def get_file_manager_settings(
    file_manager_name: str,
    cats: ContextualCats = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified File Manager"""

    ccat = cats.cheshire_cat
    factory = FileManagerFactory(ccat.plugin_manager)
    return get_factory_setting(ccat.id, file_manager_name, factory)


@router.put("/settings/{file_manager_name}", response_model=UpsertSettingResponse)
async def upsert_file_manager_setting(
    file_manager_name: str,
    payload: Dict = Body(...),
    cats: ContextualCats = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.EDIT),
) -> ReplacedNLPConfig:
    """Upsert the File Manager setting"""

    ccat = cats.cheshire_cat
    on_upsert_factory_setting(file_manager_name, FileManagerFactory(ccat.plugin_manager))

    return ccat.replace_file_manager(file_manager_name, payload)
