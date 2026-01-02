from typing import Dict, List, Annotated
import jwt
from fastapi import APIRouter, Depends

from cat.auth.auth_utils import DEFAULT_JWT_ALGORITHM
from cat.auth.permissions import get_full_permissions
from cat.env import get_env
from cat.routes.routes_utils import UserCredentials, JWTResponse, create_jwt_content
from cat.services.redis_search import RedisSearchService, get_redis_search_service

router = APIRouter(tags=["User Auth"], prefix="/auth")


@router.get("/available-permissions", response_model=Dict[str, List[str]])
async def get_available_permissions() -> Dict[str, List[str]]:
    """Returns all available resources and permissions."""
    permissions = get_full_permissions()
    return {resource: perms for resource, perms in permissions.items()}


@router.post("/token", response_model=JWTResponse)
async def auth_token(
    credentials: UserCredentials,
    redis_search_service: Annotated[RedisSearchService, Depends(get_redis_search_service)],
) -> JWTResponse:
    """Endpoint called from client to get a JWT from local identity provider.
    This endpoint receives username and password as form-data, validates credentials and issues a JWT.
    """
    jwt_content = await create_jwt_content(credentials, redis_search_service)

    access_token = jwt.encode(jwt_content, get_env("CCAT_JWT_SECRET"), algorithm=DEFAULT_JWT_ALGORITHM)
    return JWTResponse(access_token=access_token)
