import os
from typing import List, Dict, Any
from fastapi import Request
from pydantic import BaseModel, Field, model_validator

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
from cat.exceptions import CustomValidationException, CustomNotFoundException
from cat.services.memory.models import VectorMemoryType


class DeleteConversationHistoryResponse(BaseModel):
    deleted: bool


class GetConversationHistoryResponse(BaseModel):
    history: List[ConversationMessage]


class PutConversationAttributes(BaseModel):
    name: str | None = None
    metadata: Dict[str, Any] | None = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_metadata(self):
        if self.metadata is None:
            self.metadata = {}
        if self.name is None and not self.metadata:
            raise ValueError("Either name or metadata must be provided")
        return self


class PutConversationResponse(BaseModel):
    changed: bool


class GetConversationsResponse(BaseModel):
    chat_id: str
    name: str
    num_messages: int
    metadata: Dict[str, Any]
    created_at: float | None
    updated_at: float | None


def _resolve_ids(info: AuthorizedInfo, request: Request):
    """Return (agent_id, user_id) resolving user from X-User-ID header when present.

    The header is sent by both the SDK and the admin UI. When an admin selects
    a different user in the UI, X-User-ID contains that user's id while the JWT
    belongs to the admin — so we must prefer the header over info.user.id.
    Fallback to info.user.id keeps existing chatbot flows intact.
    """
    agent_id = info.cheshire_cat.agent_key if info.cheshire_cat else info.lizard.agent_key
    header_user_id = request.headers.get("X-User-ID")
    user_id = header_user_id or info.user.id
    return agent_id, user_id


# DELETE conversation
@endpoint.delete(
    "/{chat_id}",
    response_model=DeleteConversationHistoryResponse,
    tags=["Conversation"],
    prefix="/conversations",
)
async def delete_conversation(
    chat_id: str,
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> DeleteConversationHistoryResponse:
    """Delete the specified conversation and all related files and vector memories."""
    agent_id, user_id = _resolve_ids(info, request)
    cat = info.cheshire_cat

    try:
        # delete the files related to the conversation from the storage
        cat.file_manager.remove_folder(os.path.join(agent_id, chat_id))

        # delete the elements of the conversation from the vector memory
        await cat.vector_memory_handler.delete_tenant_points(
            str(VectorMemoryType.EPISODIC), {"chat_id": chat_id},
        )

        # Delete conversation from the database
        await crud_conversations.delete_conversation(agent_id, user_id, chat_id)

        return DeleteConversationHistoryResponse(deleted=True)
    except Exception as e:
        raise CustomValidationException(f"Failed to delete conversation {chat_id}: {e}")


# GET conversation history — reads from Redis, no active WS session required
@endpoint.get(
    "/{chat_id}/history",
    response_model=GetConversationHistoryResponse,
    tags=["Conversation"],
    prefix="/conversations",
)
async def get_conversation_history(
    chat_id: str,
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> GetConversationHistoryResponse:
    """Get the specified conversation history from Redis."""
    agent_id, user_id = _resolve_ids(info, request)
    messages_raw = await crud_conversations.get_messages(agent_id, user_id, chat_id)
    if messages_raw is None:
        raise CustomNotFoundException(f"Conversation '{chat_id}' not found")
    messages = [
        ConversationMessage(**m) if isinstance(m, dict) else m
        for m in messages_raw
    ]
    return GetConversationHistoryResponse(history=messages)


# GET single conversation attributes
@endpoint.get(
    "/{chat_id}",
    response_model=GetConversationsResponse,
    tags=["Conversation"],
    prefix="/conversations",
)
async def get_conversation(
    chat_id: str,
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> GetConversationsResponse:
    """Get the specified conversation attributes from Redis."""
    agent_id, user_id = _resolve_ids(info, request)
    attributes = await crud_conversations.get_conversation_attributes(agent_id, user_id, chat_id)
    if attributes is None:
        raise CustomNotFoundException("Conversation not found")
    return GetConversationsResponse(**attributes)


# PUT conversation name or metadata
@endpoint.put(
    "/{chat_id}",
    response_model=PutConversationResponse,
    tags=["Conversation"],
    prefix="/conversations",
)
async def change_attribute_conversation(
    chat_id: str,
    payload: PutConversationAttributes,
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.WRITE),
) -> PutConversationResponse:
    """Update name and/or metadata of the specified conversation."""
    agent_id, user_id = _resolve_ids(info, request)
    await crud_conversations.set_attributes(
        agent_id, user_id, chat_id, name=payload.name, metadata=payload.metadata,
    )
    return PutConversationResponse(changed=True)


# GET all conversations list
@endpoint.get(
    "/",
    response_model=List[GetConversationsResponse],
    tags=["Conversation"],
    prefix="/conversations",
)
async def get_conversations(
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> List[GetConversationsResponse]:
    """Get all conversations for the specified user."""
    agent_id, user_id = _resolve_ids(info, request)
    attributes_list = await crud_conversations.get_conversations_attributes(agent_id, user_id)
    return [GetConversationsResponse(**item) for item in attributes_list]
