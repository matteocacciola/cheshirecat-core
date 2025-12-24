import json
from typing import Dict, List
import jwt
from fastapi import APIRouter, Body, Request
from fastapi_healthz import HealthCheckRegistry, HealthCheckRedis, health_check_route
from pydantic import BaseModel, Field

from cat.auth.auth_utils import is_jwt, extract_token_from_request, check_password
from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.db.crud import get_db_connection_string
from cat.db.cruds import users as crud_users
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.exceptions import CustomUnauthorizedException, CustomNotFoundException
from cat.looking_glass import StrayCat, ChatResponse
from cat.memory.messages import UserMessage
from cat.routes.routes_utils import HealthCheckLocal

router = APIRouter()

# Add Health Checks
_healthChecks = HealthCheckRegistry()
_healthChecks.add_many([
    HealthCheckLocal(),
    HealthCheckRedis(get_db_connection_string())
])

router.add_api_route(
    "/health/readiness",
    endpoint=health_check_route(registry=_healthChecks),
    methods=["GET"],
    name="readiness_probe",
    include_in_schema=False,
)

router.add_api_route(
    "/health/liveness",
    endpoint=health_check_route(registry=_healthChecks),
    methods=["GET"],
    name="liveness_probe",
    include_in_schema=False,
)


class User(BaseModel):
    id: str
    username: str
    permissions: Dict[str, List[str]]


class AgentMatch(BaseModel):
    agent_id: str
    agent_name: str
    agent_description: str | None = None
    user: User


class MeResponse(BaseModel):
    success: bool
    agents: List[AgentMatch] = Field(default_factory=list)
    auto_selected: bool


@router.get("/", name="index", include_in_schema=False)
async def home() -> str:
    return "We're all mad here, dear!"


@router.post("/message", response_model=ChatResponse, tags=["Message"])
async def http_chat(
    payload: Dict = Body(...),
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.WRITE, is_chat=True),
) -> ChatResponse:
    """Get a response from the Cat"""
    stray_cat = info.stray_cat or StrayCat(user_data=info.user, agent_id=info.cheshire_cat.id)

    user_message = UserMessage(**payload)
    answer = await stray_cat.run_http(user_message)
    return answer


@router.get("/me", response_model=MeResponse)
async def me(request: Request) -> MeResponse:
    token = extract_token_from_request(request)
    if token is None:
        raise CustomUnauthorizedException("Unauthorized")

    if not is_jwt(token):
        raise CustomNotFoundException("Not Found")

    username = jwt.decode(token, options={"verify_signature": False})["sub"]
    password = ""

    matches_raw = crud_users.username_search(username)
    if not matches_raw:
        raise CustomUnauthorizedException("Invalid Credentials")

    valid_agents = []
    for match_str in matches_raw:
        match = json.loads(match_str)
        stored_hash = match["user"]["password"]

        # Verify password with bcrypt
        if check_password(password, stored_hash) and match["agent_id"] != DEFAULT_SYSTEM_KEY:
            valid_agents.append(AgentMatch(
                agent_id=match["agent_id"],
                agent_name=match["agent_name"],
                agent_description=match.get("agent_description"),
                user=User(**match["user"])
            ))

    return MeResponse(
        success=True,
        agents=valid_agents,
        auto_selected=len(valid_agents) == 1
    )
