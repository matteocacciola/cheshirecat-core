from abc import ABC, abstractmethod
from typing import List, Dict
from langchain_core.tools import StructuredTool
from pydantic import Field

from cat.utils import Enum


class CatProcedureType(Enum):
    FORM = "form"
    TOOL = "tool"
    MCP = "mcp"


class CatProcedure(ABC):
    name: str
    description: str | None = None
    input_schema: Dict = Field(default_factory=dict)
    output_schema: Dict = Field(default_factory=dict)
    examples: List[str] | None = Field(default_factory=list)
    plugin_id: str | None = None

    stray = None

    @abstractmethod
    def langchainfy(self) -> List[StructuredTool]:
        """
        Convert CatProcedure into a langchain compatible StructuredTool object.

        Returns
        -------
        List[StructuredTool]
            The langchain compatible StructuredTool objects.
        """
        pass

    @property
    @abstractmethod
    def type(self) -> CatProcedureType:
        pass
