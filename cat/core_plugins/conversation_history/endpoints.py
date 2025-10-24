from typing import List, Literal, Dict
from pydantic import BaseModel

from cat import (
    AuthorizedInfo,
    AuthPermission,
    AuthResource,
    CatMessage,
    ConversationHistoryItem,
    MessageWhy,
    check_permissions,
    endpoint,
    UserMessage,
)
from cat.db.cruds import history as crud_history


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
    "/{chat_id}",
    response_model=DeleteConversationHistoryResponse,
    tags=["Conversation History"],
    prefix="/conversation",
)
async def destroy_conversation_history(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> DeleteConversationHistoryResponse:
    """Delete the specified user's conversation history from working memory"""
    info.stray_cat.working_memory.reset_history()

    return DeleteConversationHistoryResponse(deleted=True)


# GET conversation history from working memory
@endpoint.get(
    "/{chat_id}",
    response_model=GetConversationHistoryResponse,
    tags=["Conversation History"],
    prefix="/conversation",
)
async def get_conversation_history(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> GetConversationHistoryResponse:
    """Get the specified user's conversation history from working memory"""
    return GetConversationHistoryResponse(history=info.stray_cat.working_memory.history)


# PUT conversation history into working memory
@endpoint.post(
    "/{chat_id}",
    response_model=GetConversationHistoryResponse,
    tags=["Conversation History"],
    prefix="/conversation",
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


# GET all conversation history from working memory
@endpoint.get(
    "/",
    response_model=Dict[str, GetConversationHistoryResponse],
    tags=["Conversation History"],
    prefix="/conversation",
)
async def get_conversation_histories(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> Dict[str, GetConversationHistoryResponse]:
    """Get the specified user's conversation history from working memory"""
    histories = crud_history.get_histories(info.cheshire_cat.id, info.user.id)

    response = {
        chat_id: GetConversationHistoryResponse(
            history=[ConversationHistoryItem(**item, chat_id=chat_id) for item in history]
        )
        for chat_id, history in histories.items()
    }

    return response
