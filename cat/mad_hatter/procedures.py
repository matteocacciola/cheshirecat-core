from abc import ABC, abstractmethod
from typing import List
from pydantic import Field

from langchain_core.tools import StructuredTool


class CatProcedure(ABC):
    name: str
    description: str | None = None
    start_examples: List[str] | None = Field(default_factory=list)
    plugin_id: str | None = None

    @abstractmethod
    def langchainfy(self) -> List[StructuredTool]:
        """
        Convert CatProcedure to a langchain compatible StructuredTool object.

        Returns
        -------
        List[StructuredTool]
            The langchain compatible StructuredTool objects.
        """
        pass
