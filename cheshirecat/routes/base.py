from fastapi import APIRouter, Body
from typing import Dict
from pydantic import BaseModel

from cheshirecat.auth.permissions import AuthPermission, AuthResource, check_message_permissions
from cheshirecat.auth.connection import AuthorizedInfo
from cheshirecat.memory.messages import CatMessage, UserMessage
from cheshirecat.looking_glass import StrayCat
from cheshirecat.utils import get_cat_version

router = APIRouter()


class HomeResponse(BaseModel):
    status: str
    version: str


# server status
@router.get("/", response_model=HomeResponse, tags=["Home"])
async def home() -> HomeResponse:
    """Server status"""
    return HomeResponse(status="We're all mad here, dear!", version=get_cat_version())


@router.post("/message", response_model=CatMessage, tags=["Message"])
async def message_with_cat(
    payload: Dict = Body(...),
    info: AuthorizedInfo = check_message_permissions(AuthResource.CONVERSATION, AuthPermission.WRITE),
) -> CatMessage:
    """Get a response from the Cat"""
    stray = StrayCat(user_data=info.user, agent_id=info.cheshire_cat.id)

    user_message = UserMessage(**payload)
    answer = await stray.run_http(user_message)
    return answer
