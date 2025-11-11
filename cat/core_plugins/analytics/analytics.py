from typing import Dict, List
import tiktoken

from cat import hook, log
from cat.memory.utils import PointStruct


@hook(priority=1)
def before_cat_sends_message(message, agent_output, cat) -> Dict:
    model_interactions = cat.working_memory.model_interactions
    input_tokens = sum(interaction.input_tokens for interaction in model_interactions)
    output_tokens = sum(interaction.output_tokens for interaction in model_interactions)
    # TODO: store the elements

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

    # TODO: store the elements


# TODO: create endpoints to retrieve analytics_
# - for embedders
# - for llm -> per agent, per user, per model, per chat