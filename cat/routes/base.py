from typing import Dict
from fastapi import APIRouter, Body
from fastapi_healthz import HealthCheckRegistry, HealthCheckRedis, health_check_route

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_message_permissions
from cat.db.crud import get_db_connection_string
from cat.looking_glass import StrayCat
from cat.memory.messages import CatMessage, UserMessage
from cat.routes.routes_utils import HealthCheckLocal

router = APIRouter()

# Add Health Checks
_healthChecks = HealthCheckRegistry()
_healthChecks.add_many([
    HealthCheckLocal(),
    HealthCheckRedis(get_db_connection_string())
])

router.add_api_route(
    '/',
    endpoint=health_check_route(registry=_healthChecks),
    methods=["GET"],
    tags=["Health"],
    name="health_check",
)


@router.post("/message", response_model=CatMessage, tags=["Message"])
async def http_chat(
    payload: Dict = Body(...),
    info: AuthorizedInfo = check_message_permissions(AuthResource.CHAT, AuthPermission.WRITE),
) -> CatMessage:
    """Get a response from the Cat"""
    stray_cat = info.stray_cat or StrayCat(user_data=info.user, agent_id=info.cheshire_cat.id)

    user_message = UserMessage(**payload)
    answer = await stray_cat.run_http(user_message)
    return answer
