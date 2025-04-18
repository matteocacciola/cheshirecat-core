from fastapi import APIRouter
from pydantic import BaseModel

from cat.auth.connection import ContextualCats
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.convo.messages import ConversationHistory, MessageWhy, CatMessage, UserMessage, Role

router = APIRouter()


class DeleteConversationHistoryResponse(BaseModel):
    deleted: bool


class GetConversationHistoryResponse(BaseModel):
    history: ConversationHistory


class PostConversationHistoryPayload(BaseModel):
    who: str
    text: str
    image: str | None = None
    why: MessageWhy | None = None


# DELETE conversation history from working memory
@router.delete("/conversation_history", response_model=DeleteConversationHistoryResponse)
async def destroy_conversation_history(
    cats: ContextualCats = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> DeleteConversationHistoryResponse:
    """Delete the specified user's conversation history from working memory"""

    cats.stray_cat.working_memory.reset_history()

    return DeleteConversationHistoryResponse(deleted=True)


# GET conversation history from working memory
@router.get("/conversation_history", response_model=GetConversationHistoryResponse)
async def get_conversation_history(
    cats: ContextualCats = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> GetConversationHistoryResponse:
    """Get the specified user's conversation history from working memory"""

    return GetConversationHistoryResponse(history=cats.stray_cat.working_memory.history)


# PUT conversation history into working memory
@router.post("/conversation_history", response_model=GetConversationHistoryResponse)
async def add_conversation_history(
    payload: PostConversationHistoryPayload,
    cats: ContextualCats = check_permissions(AuthResource.MEMORY, AuthPermission.WRITE),
) -> GetConversationHistoryResponse:
    """Insert the specified conversation item into the working memory"""

    payload_dict = payload.model_dump()
    content = UserMessage(**payload_dict) if payload.who == Role.HUMAN else CatMessage(**payload_dict)

    cats.stray_cat.working_memory.update_history(Role(payload.who), content)

    return GetConversationHistoryResponse(history=cats.stray_cat.working_memory.history)
