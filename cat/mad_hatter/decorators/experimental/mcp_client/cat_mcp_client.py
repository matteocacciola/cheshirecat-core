from abc import ABC, abstractmethod
from typing import Any, List, Dict
from langchain.tools import StructuredTool
from fastmcp import Client

from cat.log import log
from cat.mad_hatter.procedures import CatProcedure
from cat.mad_hatter.decorators.tool import CatTool


class CatMcpClient(Client, CatProcedure, ABC):
    """
    Abstract base class for a MCP client.
    Plugin developers can extend this class to implement their own MCP protocol.

    Notes:
        Subclasses must implement:
        - the `init_args` property to define the input arguments for the MCP client (from the MCP sesrver)
        The `langchainfy` method converts discovered MCP procedures into LangChain StructuredTools.
        Ensure proper error handling for network issues or invalid server responses.
    """
    def __init__(self):
        init_args = self.init_args
        if isinstance(init_args, list):
            super().__init__(*init_args)
        else:
            super().__init__(**init_args)

        # Initialize CatProcedure attributes
        self.name = self.__class__.__name__
        self.description = self.__class__.__doc__ or "No description provided."
        self.input_schema = {}
        self.output_schema = {}
        self.examples = []

        # Cache for tools, prompts and resources to avoid repeated connections
        self._cached_tools = None
        self._cached_prompts = None
        self._cached_resources = None

    def langchainfy(self) -> List[StructuredTool]:
        """
        Converts discovered MCP procedures into a list of LangChain StructuredTools.
        This allows the LLM to access each individual tool on the remote server.
        """
        def build_description(p: CatProcedure) -> str:
            desc = p.description or "No description provided."
            if p.examples:
                desc += "\n\nE.g.:\n" + "\n".join(f"- {ex}" for ex in p.examples)
            return desc

        def create_tool_caller(tool_name: str):
            """Create a closure that properly calls the MCP tool."""
            def tool_caller(**kwargs):
                try:
                    from cat.looking_glass import HumptyDumpty

                    async def call_tool_async():
                        async with self:
                            return await self.call_tool(tool_name, **kwargs)

                    return HumptyDumpty.run_sync_or_async(call_tool_async)
                except Exception as e:
                    log.error(f"{self.name} - Error calling tool {tool_name}: {e}")
                    return f"Error calling tool {tool_name}: {e}"

            return tool_caller

        tools = []
        try:
            # Get tools with proper connection handling
            for tool in self.mcp_tools:
                cat_tool = CatTool.from_fastmcp(tool, self.call_tool)

                # Create a StructuredTool for each discovered procedure
                tools.append(
                    StructuredTool.from_function(
                        name=cat_tool.name,
                        description=build_description(cat_tool),
                        func=create_tool_caller(cat_tool.name),
                        args_schema=cat_tool.input_schema,
                    )
                )
        except Exception as e:
            log.error(f"{self.name} - Error creating LangChain tools: {e}")

        return tools

    def __repr__(self) -> str:
        return f"McpClient(name={self.name})"

    async def _get_mcp_tools_async(self) -> List:
        """
        Asynchronously fetch MCP tools using proper context manager.
        """
        async with self:
            return await self.list_tools()

    async def _get_mcp_prompts_async(self) -> List:
        """
        Asynchronously fetch MCP prompts using proper context manager.
        """
        async with self:
            return await self.list_prompts()

    async def _get_mcp_resources_async(self) -> List:
        """
        Asynchronously fetch MCP prompts using proper context manager.
        """
        async with self:
            return await self.list_resources()

    @property
    def mcp_tools(self):
        from cat.looking_glass import HumptyDumpty

        if self._cached_tools is None:
            self._cached_tools = HumptyDumpty.run_sync_or_async(self._get_mcp_tools_async)
        return self._cached_tools

    @property
    def mcp_prompts(self):
        from cat.looking_glass import HumptyDumpty

        if self._cached_prompts is None:
            self._cached_prompts = HumptyDumpty.run_sync_or_async(self._get_mcp_prompts_async)
        return self._cached_prompts

    @property
    def mcp_resources(self):
        from cat.looking_glass import HumptyDumpty

        if self._cached_resources is None:
            self._cached_resources = HumptyDumpty.run_sync_or_async(self._get_mcp_resources_async)
        return self._cached_resources

    @property
    @abstractmethod
    def init_args(self) -> List | Dict[str, Any]:
        """
        Define the input arguments to be passed to the constructor of the MCP client

        Returns:
            List of arguments, or a dictionary identifying each name of the arguments with the corresponding value
        """
        pass