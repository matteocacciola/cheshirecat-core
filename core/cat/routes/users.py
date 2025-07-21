from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import List, Dict
from fastapi import APIRouter

from cat.auth.permissions import AuthPermission, AuthResource, get_base_permissions, check_permissions
from cat.auth.auth_utils import hash_password
from cat.auth.connection import AuthorizedInfo
from cat.db.cruds import users as crud_users
from cat.exceptions import CustomNotFoundException, CustomForbiddenException

router = APIRouter()


class UserBase(BaseModel):
    username: str = Field(min_length=2)
    permissions: Dict[str, List[str]] = Field(default_factory=get_base_permissions)

    @field_validator("permissions")
    def validate_permissions(cls, v):
        if not v:
            raise ValueError("Permissions cannot be empty")
        # Check if all permissions are empty
        all_items_empty = all([not p for p in v.values()])
        if all_items_empty:
            raise ValueError("At least one permission must be set")
        # Validate each resource and its permissions
        for k_, v_ in v.items():
            if k_ not in AuthResource:
                raise ValueError(f"Invalid resource: {k_}")
            if any([p not in AuthPermission for p in v_]):
                raise ValueError(f"Invalid permissions for {k_}")
        return v


class UserCreate(UserBase):
    id: str | None = None
    password: str = Field(min_length=5)
    # no additional fields allowed
    model_config = ConfigDict(extra="forbid")


class UserUpdate(UserBase):
    username: str = Field(default=None, min_length=2)
    password: str = Field(default=None, min_length=4)
    permissions: Dict[str, List[str]] = None
    model_config = ConfigDict(extra="forbid")

    @field_validator("permissions")
    def validate_permissions(cls, v):
        if v is None:
            return v
        return super().validate_permissions(v)


class UserResponse(UserBase):
    id: str


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
    stored_user = crud_users.get_user(agent_id, user_id)
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
