import re
import string
from abc import ABC
from itertools import combinations
from typing import Type, List
from langchain_core.embeddings import Embeddings
from pydantic import ConfigDict
from sklearn.feature_extraction.text import CountVectorizer

from cat.factory.base_factory import BaseFactory, BaseFactoryConfigModel


class DumbEmbedder(Embeddings):
    """Default Dumb Embedder.

    This is the default embedder used for testing purposes
    and to replace official embedders when they are not available.

    Notes
    -----
    This class relies on the `CountVectorizer`[1]_ offered by Scikit-learn.
    This embedder uses a naive approach to extract features from a text and build an embedding vector.
    Namely, it looks for pairs of characters in text starting form a vocabulary with all possible pairs of
    printable characters, digits excluded.
    """
    def __init__(self):
        # Get all printable characters numbers excluded and make everything lowercase
        chars = [p.lower() for p in string.printable[10:]]

        # Make the vocabulary with all possible combinations of 2 characters
        voc = sorted(set([f"{k[0]}{k[1]}" for k in combinations(chars, 2)]))

        # Naive embedder that counts occurrences of a couple of characters in text
        self.embedder = CountVectorizer(
            vocabulary=voc, analyzer=lambda s: re.findall("..", s), binary=True
        )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed a list of text and returns the embedding vectors that are lists of floats."""
        return self.embedder.transform(texts).astype(float).todense().tolist()

    def embed_query(self, text: str) -> List[float]:
        """Embed a string of text and returns the embedding vector as a list of floats."""
        return self.embed_documents([text])[0]


class EmbedderSettings(BaseFactoryConfigModel, ABC):
    _is_multimodal: bool = False

    # This is related to pydantic, because "model_*" attributes are protected.
    # We deactivate the protection because langchain relies on several "model_*" named attributes
    model_config = ConfigDict(protected_namespaces=())

    @classmethod
    def base_class(cls) -> Type:
        return Embeddings

    @classmethod
    def is_multimodal(cls) -> bool:
        return cls._is_multimodal.default


class EmbedderMultimodalSettings(EmbedderSettings, ABC):
    _is_multimodal: bool = True


class EmbedderDumbConfig(EmbedderSettings):
    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Dumb Embedder",
            "description": "Configuration for default embedder. It encodes the pairs of characters",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type:
        return DumbEmbedder


class EmbedderFactory(BaseFactory):
    def get_allowed_classes(self) -> List[Type[EmbedderSettings]]:
        list_embedder = self._hook_manager.execute_hook(
            "factory_allowed_embedders", [EmbedderDumbConfig], cat=None
        )
        return list_embedder

    @property
    def setting_name(self) -> str:
        return "embedder_selected"

    @property
    def setting_category(self) -> str:
        return "embedder"

    @property
    def setting_factory_category(self) -> str:
        return "embedder_factory"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return EmbedderDumbConfig

    @property
    def schema_name(self) -> str:
        return "languageEmbedderName"
