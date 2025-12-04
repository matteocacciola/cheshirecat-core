from typing import List, Dict
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, ConfigDict, field_validator

from cat.auth.auth_utils import hash_password
from cat.auth.permissions import AdminAuthResource, AuthPermission, get_full_admin_permissions, check_admin_permissions
from cat.db.cruds import users as crud_users
from cat.exceptions import CustomNotFoundException, CustomForbiddenException
from cat.looking_glass import BillTheLizard
from cat.routes.routes_utils import validate_permissions as fnc_validate_permissions

router = APIRouter(tags=["Admins"], prefix="/users")


class AdminBase(BaseModel):
    username: str = Field(min_length=5)
    permissions: Dict[str, List[str]] = Field(default_factory=get_full_admin_permissions)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v):
        return fnc_validate_permissions(v, AdminAuthResource)


class AdminBaseRequest(AdminBase):
    def __init__(self, **data):
        super().__init__(**data)
        # Ensure to attach all permissions for 'me'
        if not self.permissions:
            self.permissions = {}
        self.permissions[str(AdminAuthResource.ME)] = [str(p) for p in AuthPermission]


class AdminCreate(AdminBaseRequest):
    password: str = Field(min_length=5)
    # no additional fields allowed
    model_config = ConfigDict(extra="forbid")


class AdminUpdate(AdminBaseRequest):
    password: str = Field(default=None, min_length=5)
    permissions: Dict[str, List[str]] = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v):
        if v is None:
            return v
        return super().validate_permissions(v)


class AdminResponse(AdminBase):
    id: str

    def __init__(self, **data):
        super().__init__(**data)
        self.permissions.pop(str(AdminAuthResource.ME), None)


@router.post("/", response_model=AdminResponse)
async def create_admin(
    new_user: AdminCreate,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.ADMINS, AuthPermission.WRITE),
):
    created_user = crud_users.create_user(lizard.config_key, new_user.model_dump())
    if not created_user:
        raise CustomForbiddenException("Cannot duplicate admin")

    return created_user


@router.get("/", response_model=List[AdminResponse])
async def read_admins(
    skip: int = Query(default=0, description="How many admins to skip."),
    limit: int = Query(default=100, description="How many admins to return."),
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.ADMINS, AuthPermission.LIST),
):
    users_db = crud_users.get_users(lizard.config_key)

    users = list(users_db.values())[skip:(skip + limit)]
    return users


@router.get("/{user_id}", response_model=AdminResponse)
async def read_admin(
    user_id: str,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.ADMINS, AuthPermission.READ),
):
    users_db = crud_users.get_users(lizard.config_key)

    if user_id not in users_db:
        raise CustomNotFoundException("User not found")
    return users_db[user_id]


@router.put("/{user_id}", response_model=AdminResponse)
async def update_admin(
    user_id: str,
    user: AdminUpdate,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.ADMINS, AuthPermission.EDIT),
):
    stored_user = crud_users.get_user(lizard.config_key, user_id, full=True)
    if not stored_user:
        raise CustomNotFoundException("User not found")
    
    if user.password:
        user.password = hash_password(user.password)
    updated_info = {**stored_user, **user.model_dump(exclude_unset=True)}

    crud_users.update_user(lizard.config_key, user_id, updated_info)
    return updated_info


@router.delete("/{user_id}", response_model=AdminResponse)
async def delete_admin(
    user_id: str,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.ADMINS, AuthPermission.DELETE),
):
    deleted_user = crud_users.delete_user(lizard.config_key, user_id)
    if not deleted_user:
        raise CustomNotFoundException("User not found")

    return deleted_user
