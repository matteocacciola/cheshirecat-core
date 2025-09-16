from abc import ABC, abstractmethod
from typing import Any, List, Dict
from langchain.tools import StructuredTool
from pydantic import BaseModel, Field

from cat.log import log
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

    Args:
        cat: The CheshireCat instance providing access to the framework's context.

    Notes:
        Subclasses must implement `discover_procedures`, `call_procedure` and `call_procedure_async` methods.
        - `discover_procedures`: Should query the remote MCP server to retrieve available procedures and
          their metadata, returning a list of `CatMcpDiscoveredProcedure` instances.
        - `call_procedure`: Should execute a specified procedure on the remote MCP server with given arguments.
        - `call_procedure_async`: Optional async version of `call_procedure` for async-compatible subclasses.

        Ensure proper error handling for network issues or invalid server responses.
    """
    def __init__(self, cat = None):
        if not hasattr(self, "name") or not self.name:
            self.name = type(self).__name__

        self._stray = cat
        try:
            self._discovered_procedures: List[CatMcpDiscoveredProcedure] = self.discover_procedures()
        except Exception as e:
            log.error(f"{self.name} - Failed to discover procedures: {e}")
            self._discovered_procedures = []

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

        def safe_call_procedure(procedure_name: str, **kwargs: Any) -> Any:
            try:
                return self.call_procedure(procedure_name=procedure_name, **kwargs)
            except Exception as e:
                log.error(f"{self.name} - Error calling procedure {procedure_name}: {e}")
                return {"error": str(e)}

        tools = []
        for procedure in self._discovered_procedures:
            # Create a StructuredTool for each discovered procedure
            tools.append(
                StructuredTool.from_function(
                    name=procedure.name,
                    description=build_description(procedure),
                    func=lambda **kwargs: safe_call_procedure(procedure_name=procedure.name, **kwargs),
                    args_schema=procedure.request_model if procedure.request_model else None,
                )
            )
        return tools

    def refresh_procedures(self) -> None:
        """Refreshes the list of discovered procedures from the MCP server."""
        self._discovered_procedures = self.discover_procedures()

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
    def call_procedure(self, procedure_name: str, **kwargs: Any) -> Any:
        """
        Executes a procedure on the remote MCP server if it exists.
        This method must be implemented by the concrete class.
        """
        pass

    @abstractmethod
    async def call_procedure_async(self, procedure_name: str, **kwargs: Any) -> Any:
        """
        Optional async version of call_procedure for async-compatible subclasses.
        """
        pass

    def __repr__(self) -> str:
        return f"McpClient(name={self.name})"
