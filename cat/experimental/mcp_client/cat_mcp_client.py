from abc import ABC, abstractmethod
from typing import Any, List, Dict
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from cat.mad_hatter import CatProcedure


class CatMcpDiscoveredProcedure(BaseModel):
    name: str
    description: str | None = None
    parameters: Dict[str, Any] | None = Field(default_factory=dict)
    request_model: Any
    response_model: Any
    return_type: Any | None = None
    examples: List[str] = Field(default_factory=list)


class CatMcpClient(CatProcedure, ABC):
    """
    Abstract base class for a tool that acts as a client for a remote MCP server.
    Plugin developers can extend this class to implement their own MCP protocol.
    """
    def __init__(self, cat):
        self._stray = cat
        self._discovered_procedures: List[CatMcpDiscoveredProcedure] = self.discover_procedures()

    def langchainfy(self) -> List[StructuredTool]:
        """
        Converts discovered MCP procedures into a list of LangChain StructuredTools.
        This allows the LLM to access each individual tool on the remote server.
        """
        def build_description(p) -> str:
            desc = p.description or "No description provided."
            if p.examples:
                desc += "\n\nE.g.:\n" + "\n".join(f"- {ex}" for ex in p.examples)
            return desc

        tools = []
        for procedure in self._discovered_procedures:
            # Create a StructuredTool for each discovered procedure
            tools.append(
                StructuredTool.from_function(
                    name=procedure.name,
                    description=build_description(procedure),
                    func=lambda **kwargs: self._execute_remote_procedure(procedure_name=procedure.name, **kwargs),
                    args_schema=procedure.request_model if procedure.request_model else None,
                )
            )
        return tools

    @abstractmethod
    def discover_procedures(self) -> List[CatMcpDiscoveredProcedure]:
        """
        Discovers the procedures available on the remote MCP server and stores them.
        This method must be implemented by the concrete class.

        Returns
        -------
        List[CatMcpDiscoveredProcedure]
            A list of discovered procedures with their metadata.
        """
        pass

    @abstractmethod
    def _execute_remote_procedure(self, procedure_name: str, **kwargs: Any) -> Any:
        """
        Executes a procedure on the remote MCP server if it exists.
        This method must be implemented by the concrete class.
        """
        pass

    def __repr__(self) -> str:
        return f"McpClient(name={self.name})"
