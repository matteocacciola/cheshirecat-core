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

    def dictify(self) -> List[Dict]:
        """
        Convert CatProcedure into a dictionary representation.

        This method must be overridden by any concrete subclass. It serves as a standard
        interface to ensure consistent dictionary output across different implementations.

        Returns:
            List[Dict]: List of dictionaries representing the procedure.
        """
        triggers_map = {
            "description": [f"{self.name}: {self.description}"],
            "examples": self.examples,
        }

        return [
            {
                "source": self.name,
                "type": str(self.type),
                "trigger_type": trigger_type,
                "content": trigger_content,
            }
            for trigger_type, trigger_list in triggers_map.items()
            for trigger_content in trigger_list
        ]

    @property
    @abstractmethod
    def type(self) -> CatProcedureType:
        pass
