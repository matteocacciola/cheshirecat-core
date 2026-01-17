import os
from typing import List
from pydantic import BaseModel

from cat import (
    AuthorizedInfo,
    AuthPermission,
    AuthResource,
    ConversationMessage,
    check_permissions,
    endpoint,
    log,
)
from cat.db.cruds import conversations as crud_conversations
from cat.exceptions import CustomValidationException
from cat.services.memory.models import VectorMemoryType


class DeleteConversationHistoryResponse(BaseModel):
    deleted: bool


class GetConversationHistoryResponse(BaseModel):
    history: List[ConversationMessage]


class PostConversationPayload(BaseModel):
    name: str


class PostConversationResponse(BaseModel):
    changed: bool


class GetConversationsResponse(BaseModel):
    chat_id: str
    name: str
    num_messages: int
    created_at: float | None
    updated_at: float | None


# DELETE conversation
@endpoint.delete(
    "/{chat_id}",
    response_model=DeleteConversationHistoryResponse,
    tags=["Conversation"],
    prefix="/conversation",
)
async def delete_conversation(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> DeleteConversationHistoryResponse:
    """Delete the specified user's conversation"""
    stray_cat = info.stray_cat
    if not stray_cat:
        log.warning("Trying to change conversation name but no StrayCat found in AuthorizedInfo")
        return DeleteConversationHistoryResponse(deleted=False)

    cat = info.cheshire_cat
    try:
        # delete the files related to the conversation from the storage
        cat.file_manager.remove_folder_from_storage(os.path.join(cat.agent_key, stray_cat.id))

        # delete the elements of the conversation from the vector memory
        await cat.vector_memory_handler.delete_tenant_points(
            str(VectorMemoryType.DECLARATIVE), {"chat_id": stray_cat.id},
        )

        # Delete conversation from the database
        crud_conversations.delete_conversation(stray_cat.agent_key, stray_cat.user.id, stray_cat.id)

        return DeleteConversationHistoryResponse(deleted=True)
    except Exception as e:
        raise CustomValidationException(f"Failed to delete conversation {stray_cat.id}: {e}")


# GET conversation history from working memory
@endpoint.get(
    "/{chat_id}",
    response_model=GetConversationHistoryResponse,
    tags=["Conversation"],
    prefix="/conversation",
)
async def get_conversation_history(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> GetConversationHistoryResponse:
    """Get the specified user's conversation history from working memory"""
    return GetConversationHistoryResponse(history=info.stray_cat.working_memory.history)


# POST conversation name change
@endpoint.post(
    "/{chat_id}",
    response_model=PostConversationResponse,
    tags=["Conversation"],
    prefix="/conversation",
)
async def change_name_conversation(
    payload: PostConversationPayload,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.WRITE),
) -> PostConversationResponse:
    """Insert the specified conversation item into the working memory"""
    if not info.stray_cat:
        log.warning("Trying to change conversation name but no StrayCat found in AuthorizedInfo")
        return PostConversationResponse(changed=False)

    cat = info.stray_cat

    crud_conversations.set_name(cat.agent_key, cat.user.id, cat.id, payload.name)
    return PostConversationResponse(changed=True)


# GET all conversations, in the format of IDs and names
@endpoint.get(
    "/",
    response_model=List[GetConversationsResponse],
    tags=["Conversation"],
    prefix="/conversation",
)
async def get_conversations_ids(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> List[GetConversationsResponse]:
    """Get the specified user's conversation history from working memory"""
    agent_id = info.cheshire_cat.agent_key
    user_id = info.user.id
    attributes_list = crud_conversations.get_conversations_attributes(agent_id, user_id)

    return [GetConversationsResponse(**attributes_item) for attributes_item in attributes_list]
