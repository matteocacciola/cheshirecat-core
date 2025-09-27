import base64
import os
from typing import Type, List
from pydantic import ConfigDict
import httpx

from cat.factory.embedder import MultimodalEmbeddings, EmbedderMultimodalSettings
from cat.utils import retrieve_image


class CustomJinaMultimodalEmbedder(MultimodalEmbeddings):
    """Use Jina AI to serve embedding multimodal models."""
    def __init__(self, base_url: str, model: str, api_key: str, task: str = "text-matching"):
        self.url = os.path.join(base_url, "v1/embeddings")
        self.model = model
        self.api_key = api_key
        self.headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        self.task = task

    def _embed(
        self,
        texts: List[str] | None = None,
        images: List[str | bytes] | None = None
    ) -> List[List[float]]:
        def parse_image(image: str | bytes) -> str:
            if isinstance(image, bytes):
                return base64.b64encode(image).decode("utf-8")
            image = retrieve_image(image)
            # remove "data:image/...;base64," prefix if present
            if image is not None and image.startswith("data:image"):
                image = image.split(",", 1)[1]
            return image

        payload = (
            [{"text": t} for t in texts] if texts else []
        ) + (
            [{"image": parse_image(i)} for i in images if i] if images else []
        )

        if not payload:
            return []

        ret = httpx.post(
            self.url,
            json={"model": self.model, "input": payload, "task": self.task},
            headers=self.headers,
            timeout=300.0,
        )
        ret.raise_for_status()
        return [e["embedding"] for e in ret.json()["data"]]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._embed(texts=[text])[0]

    def embed_image(self, image: str | bytes) -> List[float]:
        return self._embed(images=[image])[0]

    def embed_images(self, images: List[str | bytes]) -> List[List[float]]:
        return self._embed(images=images)


class EmbedderJinaMultimodalConfig(EmbedderMultimodalSettings):
    base_url: str
    model: str
    api_key: str
    task: str | None = "text-matching"

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Jina Embedder",
            "description": "Configuration for Jina embeddings",
            "link": "https://docs.jina.ai/api/jina/hub/index.html?highlight=embeddings#jina.hub.encoders.text.TextEncoder",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return CustomJinaMultimodalEmbedder
