from typing import Dict, List, Any
import tiktoken
from fastapi import Query

from cat import (
    check_permissions,
    hook,
    endpoint,
    log,
    AuthPermission,
    AuthResource,
    AuthorizedInfo,
)
import cat.core_plugins.analytics.cruds.embeddings as crud_embeddings
import cat.core_plugins.analytics.cruds.llm as crud_llm
from cat.memory.utils import PointStruct


@hook(priority=1)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
    input_tokens = 0
    output_tokens = 0
    for interaction in cat.working_memory.model_interactions:
        input_tokens += interaction.input_tokens
        if hasattr(interaction, "output_tokens"):
            output_tokens += interaction.output_tokens

    if input_tokens == 0 and output_tokens == 0:
        return message

    agent_id = cat.agent_key
    user_id = cat.user.id
    chat_id = cat.id
    llm_id = cat.large_language_model_name
    tokens = crud_llm.LLMUsedTokens(input=input_tokens, output=output_tokens)

    crud_llm.update_analytics(agent_id, user_id, chat_id, llm_id, tokens)

    return message


@hook(priority=1)
def after_rabbithole_stored_documents(source: str, stored_points: List[PointStruct], cat) -> None:
    # cl100k_base is the most common encoding for OpenAI models such as GPT-3.5, GPT-4 - what about other providers?
    tokenizer = tiktoken.get_encoding("cl100k_base")
    buffer_multiplier = 1.05  # 5% buffer instead of 20%

    total_tokens = 0
    for point in stored_points:
        try:
            page_content = point.payload.get("page_content", "")
            if page_content and isinstance(page_content, str):
                total_tokens += len(tokenizer.encode(page_content))
        except Exception as e:
            log.error(f"Error in storing analytics for stored document with id {point.id} with source {source}: {e}")

    total_tokens = int(total_tokens * buffer_multiplier)
    if total_tokens == 0:
        return

    agent_id = cat.agent_key
    embedder_id = cat.embedder_name

    crud_embeddings.update_analytics(agent_id, embedder_id, source, total_tokens)


@endpoint.get("/embedder", tags=["Analytics - Embeddings"], prefix="/analytics")
async def get_analytics_embedder(
    agent_id: str = Query(default="*", description="Agent ID or * for all"),
    embedder_id: str = Query(default="*", description="Embedder ID or * for all"),
    info: AuthorizedInfo = check_permissions(AuthResource.ANALYTICS, AuthPermission.READ),
) -> Dict[str, Dict[str, Any]]:
    """
    Get analytics data filtered by agent and/or embedder.

    Examples:
    - /analytics?agent_id=agent_1&embedder_id=embedder_1
    - /analytics?agent_id=*&embedder_id=embedder_1
    - /analytics?agent_id=agent_1&embedder_id=*
    - /analytics (returns all)

    Returns:
        Nested dictionary: {agent_id: {embedder_id: {source1: count, source2: count, ...}, total_embeddings: count}}
    """
    return crud_embeddings.get_analytics(agent_id, embedder_id)


@endpoint.get("/llm", tags=["Analytics - LLM"], prefix="/analytics")
async def get_analytics_llm(
    user_id: str = Query(default="*", description="User ID or * for all"),
    chat_id: str = Query(default="*", description="Chat ID or * for all"),
    llm_id: str = Query(default="*", description="LLM ID or * for all"),
    info: AuthorizedInfo = check_permissions(AuthResource.ANALYTICS, AuthPermission.READ),
) -> Dict[str, Dict[str, Dict[str, Dict[str, Any]]]]:
    """
    Get analytics data filtered by agent, user, chat and/or llm.

    Examples:
    - /analytics?user_id=user_1&chat_id=chat_1&llm_id=llm_1
    - /analytics?user_id=*&chat_id=chat_1&llm_id=llm_1
    - /analytics?user_id=user_1&chat_id=*&llm_id=llm_1
    - /analytics?user_id=user_1&chat_id=chat_1&llm_id=*
    - /analytics (returns all)

    Returns:
        Nested dictionary: {agent_id: {user_id: {chat_id: {llm_id: {input_tokens: count, output_tokens: count, total_tokens: count, total_calls: count}}}}}
    """
    agent_id = info.cheshire_cat.agent_key

    return crud_llm.get_analytics(agent_id, user_id, chat_id, llm_id)
