import os
from typing import List
import httpx
from langchain_core.embeddings import Embeddings


class CustomOpenAIEmbeddings(Embeddings):
    """Use OpenAI-compatible API as embedder (like llama-cpp-python)."""
    def __init__(self, url, model):
        self.url = os.path.join(url, "v1/embeddings")
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # OpenAI API expects JSON payload, not form data
        ret = httpx.post(self.url, json={"model": self.model, "input": texts}, timeout=300.0)
        ret.raise_for_status()
        return [e["embedding"] for e in ret.json()["data"]]

    def embed_query(self, text: str) -> List[float]:
        # OpenAI API expects JSON payload, not form data
        ret = httpx.post(self.url, json={"model": self.model, "input": text}, timeout=300.0)
        ret.raise_for_status()
        return ret.json()["data"][0]["embedding"]


class CustomOllamaEmbeddings(Embeddings):
    """Use Ollama to serve embedding models."""
    def __init__(self, base_url, model):
        self.url = os.path.join(base_url, "api/embeddings")
        self.model = model

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        # Ollama doesn't support batch processing, so we need to process one by one
        embeddings = []
        for text in texts:
            ret = httpx.post(self.url, json={"model": self.model, "prompt": text}, timeout=300.0)
            ret.raise_for_status()
            embeddings.append(ret.json()["embedding"])
        return embeddings

    def embed_query(self, text: str) -> List[float]:
        ret = httpx.post(self.url, json={"model": self.model, "prompt": text}, timeout=300.0)
        ret.raise_for_status()
        return ret.json()["embedding"]
