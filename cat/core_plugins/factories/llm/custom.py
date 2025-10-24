from typing import Any
from langchain_ollama import ChatOllama
from langchain_openai.chat_models import ChatOpenAI


class CustomOpenAI(ChatOpenAI):
    url: str

    def __init__(self, **kwargs):
        super().__init__(model_kwargs={}, base_url=kwargs["url"], **kwargs)


class CustomOllama(ChatOllama):
    def __init__(self, **kwargs: Any) -> None:
        if kwargs.get("base_url", "").endswith("/"):
            kwargs["base_url"] = kwargs["base_url"][:-1]
        super().__init__(**kwargs)
