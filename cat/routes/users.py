from typing import List, Dict
from fastapi import APIRouter
from pydantic import BaseModel, Field, ConfigDict, field_validator

from cat.auth.auth_utils import hash_password
from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, get_base_permissions, check_permissions
from cat.db.cruds import users as crud_users
from cat.exceptions import CustomNotFoundException, CustomForbiddenException
from cat.routes.routes_utils import validate_permissions as fnc_validate_permissions

router = APIRouter(tags=["Users"], prefix="/users")


class UserBase(BaseModel):
    username: str = Field(min_length=4)
    permissions: Dict[str, List[str]] = Field(default_factory=get_base_permissions)

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v):
        return fnc_validate_permissions(v, AuthResource)


class UserBaseRequest(UserBase):
    def __init__(self, **data):
        permissions = data.get("permissions", {})
        # Ensure to attach all permissions for 'me'
        permissions[str(AuthResource.ME)] = [str(p) for p in AuthPermission]
        data["permissions"] = permissions

        super().__init__(**data)


class UserCreate(UserBaseRequest):
    id: str | None = None
    password: str = Field(min_length=5)
    # no additional fields allowed
    model_config = ConfigDict(extra="forbid")


class UserUpdate(UserBaseRequest):
    password: str = Field(default=None, min_length=5)
    model_config = ConfigDict(extra="forbid")


class UserResponse(UserBase):
    id: str

    def __init__(self, **data):
        super().__init__(**data)
        self.permissions.pop(str(AuthResource.ME), None)


@router.post("/", response_model=UserResponse)
async def create_user(
    new_user: UserCreate,
    info: AuthorizedInfo = check_permissions(AuthResource.USERS, AuthPermission.WRITE),
) -> UserResponse:
    agent_id = info.cheshire_cat.id
    created_user = crud_users.create_user(agent_id, new_user.model_dump())
    if not created_user:
        raise CustomForbiddenException("Cannot duplicate user")

    return UserResponse(**created_user)


@router.get("/", response_model=List[UserResponse])
async def read_users(
    skip: int = 0,
    limit: int = 100,
    info: AuthorizedInfo = check_permissions(AuthResource.USERS, AuthPermission.LIST),
) -> List[UserResponse]:
    users_db = crud_users.get_users(info.cheshire_cat.id)

    users = list(users_db.values())[skip: skip + limit]
    return [UserResponse(**u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def read_user(
    user_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.USERS, AuthPermission.READ),
) -> UserResponse:
    users_db = crud_users.get_users(info.cheshire_cat.id)

    if user_id not in users_db:
        raise CustomNotFoundException("User not found")
    return UserResponse(**users_db[user_id])


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    user: UserUpdate,
    info: AuthorizedInfo = check_permissions(AuthResource.USERS, AuthPermission.EDIT),
) -> UserResponse:
    agent_id = info.cheshire_cat.id
    stored_user = crud_users.get_user(agent_id, user_id, full=True)
    if not stored_user:
        raise CustomNotFoundException("User not found")
    
    if user.password:
        user.password = hash_password(user.password)
    updated_info = {**stored_user, **user.model_dump(exclude_unset=True)}

    crud_users.update_user(agent_id, user_id, updated_info)
    return UserResponse(**updated_info)


@router.delete("/{user_id}", response_model=UserResponse)
async def delete_user(
    user_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.USERS, AuthPermission.DELETE),
) -> UserResponse:
    agent_id = info.cheshire_cat.id
    deleted_user = crud_users.delete_user(agent_id, user_id)
    if not deleted_user:
        raise CustomNotFoundException("User not found")

    return UserResponse(**deleted_user)


@router.get("/me", response_model=UserBase)
async def me(
    info: AuthorizedInfo = check_permissions(AuthResource.ME, AuthPermission.READ),
) -> UserBase:
    user = info.user

    return UserBase(username=user.name, permissions=user.permissions)
