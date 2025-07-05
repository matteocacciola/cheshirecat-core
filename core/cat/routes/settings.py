from typing import Dict, List
from fastapi import APIRouter
from pydantic import BaseModel

from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.auth.connection import AuthorizedInfo
from cat.db import models
from cat.db.cruds import settings as crud_settings
from cat.exceptions import CustomNotFoundException

router = APIRouter()


class SettingResponse(BaseModel):
    setting: Dict


class GetSettingsResponse(BaseModel):
    settings: List[Dict]


class DeleteSettingResponse(BaseModel):
    deleted: str


@router.get("/", response_model=GetSettingsResponse)
async def get_settings(
    search: str = "",
    info: AuthorizedInfo = check_permissions(AuthResource.SETTINGS, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the entire list of settings available in the database"""

    settings = crud_settings.get_settings(info.cheshire_cat.id, search=search)

    return GetSettingsResponse(settings=settings)


@router.post("/", response_model=SettingResponse)
async def create_setting(
    payload: models.SettingBody,
    info: AuthorizedInfo = check_permissions(AuthResource.SETTINGS, AuthPermission.WRITE),
) -> SettingResponse:
    """Create a new setting in the database"""

    # complete the payload with setting_id and updated_at
    payload = models.Setting(**payload.model_dump())

    # save to DB
    new_setting = crud_settings.create_setting(info.cheshire_cat.id, payload)

    return SettingResponse(setting=new_setting)


@router.get("/{setting_id}", response_model=SettingResponse)
async def get_setting(
    setting_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.SETTINGS, AuthPermission.READ),
) -> SettingResponse:
    """Get the specific setting from the database"""

    setting = crud_settings.get_setting_by_id(info.cheshire_cat.id, setting_id)
    if not setting:
        raise CustomNotFoundException(f"No setting with this id: {setting_id}")
    return SettingResponse(setting=setting)


@router.put("/{setting_id}", response_model=SettingResponse)
async def update_setting(
    setting_id: str,
    payload: models.SettingBody,
    info: AuthorizedInfo = check_permissions(AuthResource.SETTINGS, AuthPermission.EDIT),
) -> SettingResponse:
    """Update a specific setting in the database if it exists"""

    agent_id = info.cheshire_cat.id

    # does the setting exist?
    setting = crud_settings.get_setting_by_id(agent_id, setting_id)
    if not setting:
        raise CustomNotFoundException(f"No setting with this id: {setting_id}")

    # complete the payload with setting_id and updated_at
    payload = models.Setting(**payload.model_dump())
    payload.setting_id = setting_id  # force this to be the setting_id

    # save to DB
    updated_setting = crud_settings.update_setting_by_id(agent_id, payload)

    return SettingResponse(setting=updated_setting)


@router.delete("/{setting_id}", response_model=DeleteSettingResponse)
async def delete_setting(
    setting_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.SETTINGS, AuthPermission.DELETE),
) -> DeleteSettingResponse:
    """Delete a specific setting in the database"""

    agent_id = info.cheshire_cat.id

    # does the setting exist?
    setting = crud_settings.get_setting_by_id(agent_id, setting_id)
    if not setting:
        raise CustomNotFoundException(f"No setting with this id: {setting_id}")

    # delete
    crud_settings.delete_setting_by_id(agent_id, setting_id)

    return DeleteSettingResponse(deleted=setting_id)
