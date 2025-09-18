from typing import List, Literal
from pydantic import BaseModel

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.mad_hatter.decorators import endpoint
from cat.memory.messages import ConversationHistoryItem, CatMessage, UserMessage, MessageWhy


class DeleteConversationHistoryResponse(BaseModel):
    deleted: bool


class GetConversationHistoryResponse(BaseModel):
    history: List[ConversationHistoryItem]


class PostConversationHistoryPayload(BaseModel):
    who: Literal["user", "assistant"]
    text: str
    image: str | None = None
    why: MessageWhy | None = None


# DELETE conversation history from working memory
@endpoint.delete(
    "/conversation_history",
    response_model=DeleteConversationHistoryResponse,
    tags=["Working Memory - Current Conversation"],
    prefix="/memory",
)
async def destroy_conversation_history(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> DeleteConversationHistoryResponse:
    """Delete the specified user's conversation history from working memory"""
    info.stray_cat.working_memory.reset_history()

    return DeleteConversationHistoryResponse(deleted=True)


# GET conversation history from working memory
@endpoint.get(
    "/conversation_history",
    response_model=GetConversationHistoryResponse,
    tags=["Working Memory - Current Conversation"],
    prefix="/memory",
)
async def get_conversation_history(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> GetConversationHistoryResponse:
    """Get the specified user's conversation history from working memory"""
    return GetConversationHistoryResponse(history=info.stray_cat.working_memory.history)


# PUT conversation history into working memory
@endpoint.post(
    "/conversation_history",
    response_model=GetConversationHistoryResponse,
    tags=["Working Memory - Current Conversation"],
    prefix="/memory",
)
async def add_conversation_history(
    payload: PostConversationHistoryPayload,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.WRITE),
) -> GetConversationHistoryResponse:
    """Insert the specified conversation item into the working memory"""
    payload_dict = payload.model_dump()
    content = UserMessage(**payload_dict) if payload.who == "user" else CatMessage(**payload_dict)

    info.stray_cat.working_memory.update_history(payload.who, content)

    return GetConversationHistoryResponse(history=info.stray_cat.working_memory.history)
