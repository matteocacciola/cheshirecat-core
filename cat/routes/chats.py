from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Body, Query

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions


router = APIRouter()


class Chat(BaseModel):
    id: str
    agent_id: str
    user_id: str
    updated_at: int
    title: str


class ChatCreate(BaseModel):
    title: str


@router.get("")
async def get_chats(
    query: Optional[str] = Query(None, description="Search in the chats."),
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.LIST),
) -> List[Chat]:
    """Get chats for a user, optionally filtered by a search term"""


    return chats


@router.get("/{chat_id}")
async def get_chat(
    chat_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.READ),
) -> Chat:
    """Get a specific chat by id."""



    return chat


@router.post("/")
async def create_chat(
    data: ChatCreate = Body(...),
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.WRITE),
) -> Chat:
    """Create a new chat."""

    return chat


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.DELETE),
):
    """Delete a specific chat"""


