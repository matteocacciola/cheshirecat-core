from abc import ABC, abstractmethod
from typing import Any, List, Dict
from langchain.tools import StructuredTool
from fastmcp import Client

from cat.log import log
from cat.mad_hatter.procedures import CatProcedure
from cat.mad_hatter.decorators.tool import CatTool


class CatMcpClient(Client, CatProcedure, ABC):
    """
    Abstract base class for a MCP client with elicitation support.
    Plugin developers can extend this class to implement their own MCP protocol.

    Notes:
        Subclasses must implement:
        - the `init_args` property to define the input arguments for the MCP client
        - optionally override `handle_elicitation` to customize elicitation handling
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

    def handle_elicitation(self, elicitation_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle MCP elicitations by storing the request in working memory.
        Override this method to customize elicitation handling.

        Args:
            elicitation_data: The elicitation request from the MCP server containing:
                - id: elicitation identifier
                - title: human-readable title
                - fields: list of fields to collect

        Returns:
            Dictionary mapping field names to user-provided values

        Raises:
            ElicitationRequiredException: When user input is needed
        """
        elicitation_id = elicitation_data.get("id", "unknown")

        # Check if we have stored responses in working memory
        elicitation_key = f"mcp_elicitation_{elicitation_id}"
        stored_responses = self.stray.working_memory.get(elicitation_key, {})

        responses = {}
        missing_fields = []

        for field in elicitation_data.get("fields", []):
            field_name = field.get("name")

            if field_name in stored_responses:
                responses[field_name] = stored_responses[field_name]
            else:
                missing_fields.append(field)

        if missing_fields:
            # Store pending elicitation in working memory
            self.stray.working_memory["pending_mcp_elicitation"] = {
                "mcp_client_name": self.name,
                "elicitation_id": elicitation_id,
                "elicitation_data": elicitation_data,
                "missing_fields": missing_fields
            }

            # Raise exception to signal elicitation is needed
            raise ElicitationRequiredException(
                elicitation_id=elicitation_id,
                missing_fields=missing_fields,
                elicitation_data=elicitation_data
            )

        # Clear stored responses after successful use
        if elicitation_key in self.stray.working_memory:
            del self.stray.working_memory[elicitation_key]

        return responses

    def store_elicitation_response(self, elicitation_id: str, field_name: str, value: Any, stray) -> None:
        """
        Store a response for a pending elicitation field in working memory.

        Args:
            elicitation_id: The ID of the elicitation
            field_name: The name of the field being provided
            value: The value for the field
            stray: StrayCat instance for accessing working memory
        """
        elicitation_key = f"mcp_elicitation_{elicitation_id}"

        if elicitation_key not in stray.working_memory:
            stray.working_memory[elicitation_key] = {}

        stray.working_memory[elicitation_key][field_name] = value
        log.info(f"{self.name} - Stored elicitation response for {field_name}")

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
            """Create a closure that properly calls the MCP tool with elicitation support."""
            def tool_caller(**kwargs):
                from cat.looking_glass import HumptyDumpty

                async def call_tool_async():
                    try:
                        async with self:
                            result = await self.call_tool(tool_name, **kwargs)
                            return result
                    except Exception as ex:
                        elicitation_data = getattr(ex, "elicitation_data", None)
                        if not elicitation_data:
                            raise
                        log.info(f"{self.name} - Elicitation signaled by exception payload.")
                        # Handle the elicitation - will raise ElicitationRequiredException if needed
                        responses = self.handle_elicitation(elicitation_data)
                        # If we got responses without exception, merge and retry once (internal retry)
                        kwargs.update(responses)
                        async with self:
                            return await self.call_tool(tool_name, **kwargs)

                try:
                    return HumptyDumpty.run_sync_or_async(call_tool_async)
                except ElicitationRequiredException as elx:
                    # Generate a string representative of the tool call for the elicitation context and retry prompt
                    joined_kwargs = ", ".join(f'{k}=\"{v}\"' for k, v in kwargs.items())
                    original_tool_call_str = f"{tool_name}({joined_kwargs})"

                    # Store the necessary context to restart into the hook
                    pending_data = self.stray.working_memory.get("pending_mcp_elicitation", {})
                    pending_data.update({
                        "original_tool_call": original_tool_call_str,
                        "elicitation_id": elx.elicitation_id,
                        "elicitation_data": elx.elicitation_data,
                        "missing_fields": elx.missing_fields,
                        "mcp_client_name": self.name
                    })
                    self.stray.working_memory["pending_mcp_elicitation"] = pending_data

                    first_field = elx.missing_fields[0] if elx.missing_fields else {}
                    return {
                        "status": "elicitation_required",
                        "elicitation_id": elx.elicitation_id,
                        "message": first_field.get("description", "Additional information is required"),
                        "field_name": first_field.get("name", "unknown"),
                        "fields": elx.missing_fields,
                        "tool_name": tool_name,
                        "mcp_client_name": self.name
                    }
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
        """Asynchronously fetch MCP tools using proper context manager."""
        async with self:
            return await self.list_tools()

    async def _get_mcp_prompts_async(self) -> List:
        """Asynchronously fetch MCP prompts using proper context manager."""
        async with self:
            return await self.list_prompts()

    async def _get_mcp_resources_async(self) -> List:
        """Asynchronously fetch MCP resources using proper context manager."""
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
            List of arguments, or a dictionary identifying each name with the corresponding value
        """
        pass


class ElicitationRequiredException(Exception):
    """Exception raised when an MCP tool requires elicitation from the user."""

    def __init__(self, elicitation_id: str, missing_fields: List[Dict[str, Any]], elicitation_data: Dict[str, Any]):
        self.elicitation_id = elicitation_id
        self.missing_fields = missing_fields
        self.elicitation_data = elicitation_data

        field_names = [f.get("name", "unknown") for f in missing_fields]
        message = f"Elicitation required for fields: {', '.join(field_names)}"
        super().__init__(message)
