from typing import List, Dict, Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.db.cruds import conversations as crud_conversations
from cat.exceptions import CustomNotFoundException

router = APIRouter(tags=["Conversations"], prefix="/conversations")


class ConversationResponse(BaseModel):
    chat_id: str
    name: str
    num_messages: int
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Any | None = None
    updated_at: Any | None = None


class ConversationHistoryItem(BaseModel):
    who: str
    when: Any | None = None
    content: Dict[str, Any] = Field(default_factory=dict)


class ConversationHistoryOutput(BaseModel):
    history: List[ConversationHistoryItem]


class ConversationDeleteOutput(BaseModel):
    deleted: bool


class ConversationAttributesChangeOutput(BaseModel):
    changed: bool


class ConversationAttributesRequest(BaseModel):
    name: str | None = None
    metadata: Dict[str, Any] | None = None


def _resolve_user_id(request: Request, info: AuthorizedInfo) -> str:
    """Return the user_id from X-User-ID header when present (admin impersonation),
    falling back to the authenticated user's own id."""
    return request.headers.get("X-User-ID") or info.user["id"]


@router.get("/", response_model=List[ConversationResponse])
async def get_conversations(
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> List[ConversationResponse]:
    agent_id = info.cheshire_cat.agent_key if info.cheshire_cat else info.lizard.agent_key
    user_id = _resolve_user_id(request, info)
    results = await crud_conversations.get_conversations_attributes(agent_id, user_id)
    return [ConversationResponse(**r) for r in results]


@router.get("/{chat_id}", response_model=ConversationResponse)
async def get_conversation(
    chat_id: str,
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> ConversationResponse:
    agent_id = info.cheshire_cat.agent_key if info.cheshire_cat else info.lizard.agent_key
    user_id = _resolve_user_id(request, info)
    result = await crud_conversations.get_conversation_attributes(agent_id, user_id, chat_id)
    if not result:
        raise CustomNotFoundException("Conversation not found")
    return ConversationResponse(**result)


@router.get("/{chat_id}/history", response_model=ConversationHistoryOutput)
async def get_conversation_history(
    chat_id: str,
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> ConversationHistoryOutput:
    agent_id = info.cheshire_cat.agent_key if info.cheshire_cat else info.lizard.agent_key
    user_id = _resolve_user_id(request, info)
    messages = await crud_conversations.get_messages(agent_id, user_id, chat_id)
    return ConversationHistoryOutput(
        history=[ConversationHistoryItem(**m) if isinstance(m, dict) else ConversationHistoryItem(**m.model_dump()) for m in messages]
    )


@router.put("/{chat_id}", response_model=ConversationAttributesChangeOutput)
async def put_conversation_attributes(
    chat_id: str,
    body: ConversationAttributesRequest,
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.WRITE),
) -> ConversationAttributesChangeOutput:
    agent_id = info.cheshire_cat.agent_key if info.cheshire_cat else info.lizard.agent_key
    user_id = _resolve_user_id(request, info)
    await crud_conversations.set_attributes(
        agent_id, user_id, chat_id, name=body.name, metadata=body.metadata
    )
    return ConversationAttributesChangeOutput(changed=True)


@router.delete("/{chat_id}", response_model=ConversationDeleteOutput)
async def delete_conversation(
    chat_id: str,
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> ConversationDeleteOutput:
    agent_id = info.cheshire_cat.agent_key if info.cheshire_cat else info.lizard.agent_key
    user_id = _resolve_user_id(request, info)
    await crud_conversations.delete_conversation(agent_id, user_id, chat_id)
    return ConversationDeleteOutput(deleted=True)
