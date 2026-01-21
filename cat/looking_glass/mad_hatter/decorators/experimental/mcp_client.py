from abc import ABC, abstractmethod
from typing import Any, List, Dict
from langchain_core.documents import Document as LangChainDocument
from langchain_core.tools import StructuredTool
from fastmcp import Client
from mcp.types import Tool
from slugify import slugify

from cat.log import log
from cat.looking_glass.mad_hatter.procedures import CatProcedure, CatProcedureType
from cat.services.memory.models import DocumentRecall
from cat.utils import run_sync_or_async


class CatMcpClient(Client, CatProcedure, ABC):
    """
    Abstract base class for an MCP client with elicitation support.
    Plugin developers can extend this class to implement their own MCP protocol.

    Notes:
        Subclasses must implement the `init_args` property to define the input arguments for the MCP client
    """
    def __init__(self):
        init_args = self.init_args
        if isinstance(init_args, list):
            super().__init__(*init_args)
        else:
            super().__init__(**init_args)

        # Initialize CatProcedure attributes
        self.name = slugify(self.__class__.__name__.strip(), separator="_")
        self.description = self.__class__.__doc__ or "No description provided."
        self.examples = []

        # Caches
        self._cached_tools: List[Tool] | None = None
        self._expected_tool_name: str | None = None

    def __repr__(self) -> str:
        return f"CatMcpClient(name={self.name}, tools={len(self.mcp_tools)})"

    def source_name(self, mcp_tool: Tool) -> str:
        return f"{self.name}_{mcp_tool.name}"

    @property
    def expected_tool_name(self) -> str:
        """
        Fetches the currently expected tool name.

        Returns:
            Tool: The currently expected tool name.
        """
        return self._expected_tool_name

    @expected_tool_name.setter
    def expected_tool_name(self, expected_tool_name: str):
        self._expected_tool_name = expected_tool_name

    def to_document_recall(self) -> List[DocumentRecall]:
        result = []
        for mcp_tool in self.mcp_tools:
            triggers_map = {
                "description": [mcp_tool.description or mcp_tool.name],
                "examples": self.examples,
            }

            result.extend([
                DocumentRecall(
                    document=LangChainDocument(
                        page_content=trigger_content,
                        metadata={
                            "obj_data": {
                                "__class__": self.__class__.__name__,
                                "__module__": self.__class__.__module__,
                                "input_params": {"tool_source": self.source_name(mcp_tool)},
                            },
                            "source": self.name,
                            "type": str(self.type),
                            "trigger_type": trigger_type,
                        },
                    ),
                )
                for trigger_type, trigger_list in triggers_map.items()
                for trigger_content in trigger_list
            ])
        return result

    @classmethod
    def reconstruct_from_params(cls, input_params: Dict) -> "CatProcedure":
        obj = cls()
        # set the expected tool name back to the original value, so that `langchainfy` can pick it up and add it to the
        # characteristics of the langchain `StructuredTool`
        obj.expected_tool_name = input_params["tool_source"]
        return obj

    def langchainfy(self) -> StructuredTool | None:
        def create_tool_caller(tool_name: str):
            """Create a closure that calls the MCP tool."""
            def tool_caller(**kwargs):
                async def call_tool_async():
                    async with self:
                        return await self.call_tool(tool_name, **kwargs)
                try:
                    return run_sync_or_async(call_tool_async)
                except Exception as ex:
                    log.error(f"{self.name} - Error calling tool {tool_name}: {ex}")
                    return {"error": f"Error calling tool {tool_name}: {str(ex)}"}
            return tool_caller

        for mcp_tool in self.mcp_tools:
            if self.source_name(mcp_tool) == self.expected_tool_name:
                # Convert the MCP tool to a LangChain StructuredTool
                description = mcp_tool.description or mcp_tool.name or "No description provided."
                if self.examples:
                    description += "\n\nE.g.:\n" + "\n".join(f"- {ex}" for ex in self.examples)

                return StructuredTool.from_function(
                    name=self.expected_tool_name,
                    description=description,
                    func=create_tool_caller(mcp_tool.name),
                    args_schema=mcp_tool.inputSchema,
                )

        log.warning(f"{self.name} - Tool '{self.expected_tool_name}' not found in MCP tools.")
        return None

    async def _get_mcp_tools_async(self) -> List[Tool]:
        """Asynchronously fetch MCP tools using a proper context manager."""
        async with self:
            return await self.list_tools()

    @property
    def type(self) -> CatProcedureType:
        return CatProcedureType.MCP

    @property
    def mcp_tools(self) -> List[Tool]:
        if self._cached_tools is None:
            self._cached_tools = run_sync_or_async(self._get_mcp_tools_async)
        return self._cached_tools

    @property
    @abstractmethod
    def init_args(self) -> List | Dict[str, Any]:
        """
        Define the input arguments to be passed to the constructor of the MCP client

        Returns:
            List of arguments, or a dictionary identifying each name with the corresponding value
        """
        pass


def mcp_client(cls: type[CatMcpClient]) -> CatMcpClient:
    """Decorator for MCP client classes."""
    if not hasattr(cls, "name") or cls.name is None:
        cls.name = cls.__name__

    return cls()
