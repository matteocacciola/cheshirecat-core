from typing import Dict, List
from fastapi import APIRouter

from cat.auth.permissions import get_full_admin_permissions, AdminAuthResource
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.routes.routes_utils import UserCredentials, JWTResponse, auth_token as fnc_auth_token

router = APIRouter(tags=["Admins - Auth"], prefix="/auth")


@router.get("/available-permissions", response_model=Dict[str, List[str]])
async def get_admins_available_permissions() -> Dict[str, List[str]]:
    """Returns all available resources and permissions."""
    permissions = get_full_admin_permissions()
    return {resource: perms for resource, perms in permissions.items() if resource != AdminAuthResource.ME}


@router.post("/token", response_model=JWTResponse)
async def system_auth_token(credentials: UserCredentials):
    """
    Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """
    return await fnc_auth_token(credentials, DEFAULT_SYSTEM_KEY)
