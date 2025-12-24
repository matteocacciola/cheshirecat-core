from typing import List, Dict
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, ConfigDict, field_validator

from cat.auth.auth_utils import hash_password
from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cat.db.cruds import users as crud_users
from cat.exceptions import CustomNotFoundException, CustomValidationException
from cat.routes.routes_utils import validate_permissions as fnc_validate_permissions

router = APIRouter(tags=["Admins"], prefix="/users")


class AdminBase(BaseModel):
    username: str = Field(min_length=5)
    permissions: Dict[str, List[str]] = Field(default_factory=dict)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v):
        return fnc_validate_permissions(v, AuthResource)


class AdminCreate(AdminBase):
    password: str = Field(min_length=5)
    # no additional fields allowed
    model_config = ConfigDict(extra="forbid")


class AdminUpdate(AdminBase):
    password: str = Field(default=None, min_length=5)
    model_config = ConfigDict(extra="forbid")


class AdminResponse(AdminBase):
    id: str


@router.post("/", response_model=AdminResponse)
async def create_admin(
    new_user: AdminCreate,
    info: AuthorizedInfo = check_permissions(AuthResource.ADMIN, AuthPermission.WRITE),
):
    created_user = crud_users.create_user(info.lizard.config_key, new_user.model_dump())
    if not created_user:
        raise CustomValidationException("Cannot duplicate admin")

    return created_user


@router.get("/", response_model=List[AdminResponse])
async def read_admins(
    skip: int = Query(default=0, description="How many admins to skip."),
    limit: int = Query(default=100, description="How many admins to return."),
    info: AuthorizedInfo = check_permissions(AuthResource.ADMIN, AuthPermission.LIST),
):
    users_db = crud_users.get_users(info.lizard.config_key)

    users = list(users_db.values())[skip:(skip + limit)]
    return users


@router.get("/{user_id}", response_model=AdminResponse)
async def read_admin(
    user_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.ADMIN, AuthPermission.READ),
):
    users_db = crud_users.get_users(info.lizard.config_key)

    if user_id not in users_db:
        raise CustomNotFoundException("User not found")
    return users_db[user_id]


@router.put("/{user_id}", response_model=AdminResponse)
async def update_admin(
    user_id: str,
    user: AdminUpdate,
    info: AuthorizedInfo = check_permissions(AuthResource.ADMIN, AuthPermission.EDIT),
):
    config_key = info.lizard.config_key
    stored_user = crud_users.get_user(config_key, user_id, full=True)
    if not stored_user:
        raise CustomNotFoundException("User not found")
    
    if user.password:
        user.password = hash_password(user.password)
    updated_info = {**stored_user, **user.model_dump(exclude_unset=True)}

    crud_users.update_user(config_key, user_id, updated_info)
    return updated_info


@router.delete("/{user_id}", response_model=AdminResponse)
async def delete_admin(
    user_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.ADMIN, AuthPermission.DELETE),
):
    deleted_user = crud_users.delete_user(info.lizard.config_key, user_id)
    if not deleted_user:
        raise CustomNotFoundException("User not found")

    return deleted_user
