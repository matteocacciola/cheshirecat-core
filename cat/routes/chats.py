from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Body, Query

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions


router = APIRouter()


class Chat(BaseModel):
    id: str
    user_id: str
    updated_at: int
    body: dict
    title: str


class ChatCreateUpdate(BaseModel):
    body: dict
    title: str


@router.get("")
async def get_chats(
    query: Optional[str] = Query(None, description="Search in the chats."),
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.LIST),
) -> List[Chat]:
    """Get chats for a user, optionally filtered by a search term"""


    return chats


@router.get("/{id}")
async def get_chat(
    id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.READ),
) -> Chat:
    """Get a specific chat by id."""



    return chat


@router.post("")
async def create_chat(
    data: ChatCreateUpdate = Body(...),
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.WRITE),
) -> Chat:
    """Create a new chat."""

    return chat


@router.delete("/{id}")
async def delete_chat(
    id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.CHAT, AuthPermission.DELETE),
):
    """Delete a specific chat"""


