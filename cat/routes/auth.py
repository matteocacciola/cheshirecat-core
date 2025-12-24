import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Annotated
import jwt
from fastapi import APIRouter, Depends

from cat.auth.auth_utils import DEFAULT_JWT_ALGORITHM
from cat.auth.permissions import get_full_permissions
from cat.env import get_env
from cat.exceptions import CustomUnauthorizedException
from cat.routes.routes_utils import UserCredentials, JWTResponse
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
    username = credentials.username
    password = credentials.password

    # search for user across all agents
    valid_matches = redis_search_service.search_user_by_credentials(username, password)
    if not valid_matches:
        # Invalid username or password
        # wait a little to avoid brute force attacks
        await asyncio.sleep(1)
        raise CustomUnauthorizedException("Invalid Credentials")

    # using seconds for easier testing
    expire_delta_in_seconds = float(get_env("CCAT_JWT_EXPIRE_MINUTES")) * 60
    now = datetime.now(timezone.utc)

    expires = now + timedelta(seconds=expire_delta_in_seconds)

    jwt_content = {
        "sub": username,  # Subject (the Username)
        "exp": expires,  # Expiry date as a Unix timestamp
        "iat": now,
        "agents": valid_matches,
    }
    access_token = jwt.encode(jwt_content, get_env("CCAT_JWT_SECRET"), algorithm=DEFAULT_JWT_ALGORITHM)
    return JWTResponse(access_token=access_token)
