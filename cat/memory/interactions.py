import time
from typing import Literal, List
from pydantic import BaseModel, Field, ConfigDict


class ModelInteraction(BaseModel):
    """
    Base class for interactions with models, capturing essential attributes common to all model interactions.

    Attributes
    ----------
    model_type: Literal["llm", "embedder"]
        The type of model involved in the interaction, either a large language model (LLM) or an embedder.
    source: str
        The source from which the interaction originates.
    prompt: List[str]
        The prompt or input provided to the model.
    input_tokens: int
        The number of input tokens processed by the model.
    started_at: float
        The timestamp when the interaction started. Defaults to the current time.
    """
    model_type: Literal["llm", "embedder"]
    source: str
    prompt: List[str]
    input_tokens: int
    started_at: float = Field(default_factory=lambda: time.time())

    model_config = ConfigDict(
        protected_namespaces=()
    )

    def __hash__(self):
        return hash((self.model_type, tuple(self.prompt), self.input_tokens))

    def __eq__(self, other):
        if not isinstance(other, ModelInteraction):
            return NotImplemented
        return (self.model_type, self.prompt, self.input_tokens) == (other.model_type, other.prompt, other.input_tokens)
