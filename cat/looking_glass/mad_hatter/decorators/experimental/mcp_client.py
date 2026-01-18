from abc import ABC, abstractmethod
from typing import Any, List, Dict
import numpy as np
from langchain_core.tools import StructuredTool
from fastmcp import Client
from mcp.types import Prompt, Resource, Tool
from slugify import slugify

from cat.log import log
from cat.looking_glass.mad_hatter.procedures import CatProcedure, CatProcedureType
from cat.utils import run_sync_or_async

# Global cache shared across all CatMcpClient instances
_MCP_TOOL_EMBEDDINGS_CACHE = {}


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
        self._cached_tools = None
        self._langchain_tools_cache = {}
        self._relevant_tools = []

    def _get_cache_key(self) -> str:
        """Generate a unique cache key for this MCP client's tools."""
        # Use class name and a hash of tool names to create a stable cache key
        tool_ids = sorted([t.name for t in self.mcp_tools])
        return f"{self.name}_{hash(tuple(tool_ids))}"

    def _ensure_tool_embeddings_cached(self):
        """Ensure tool embeddings are cached globally. Only embeds once per MCP client configuration."""
        cache_key = self._get_cache_key()
        if cache_key in _MCP_TOOL_EMBEDDINGS_CACHE:
            log.debug(f"{self.name} - Using cached tool embeddings")
            return

        log.debug(f"MCP Client {self.name} - Embedding {len(self.mcp_tools)} MCP tools (one-time operation)")
        embedder = self.stray.embedder

        tool_embeddings = []
        for tool in self.mcp_tools:
            # Create a searchable text combining tool name and description
            tool_text = f"{tool.name}: {tool.description or 'No description'}"
            embedding = embedder.embed_query(tool_text)
            tool_embeddings.append({
                "tool": tool,
                "embedding": embedding,
            })

        _MCP_TOOL_EMBEDDINGS_CACHE[cache_key] = tool_embeddings

    def find_relevant_tools(self, query_embeddings: List[float], top_k: int = 5) -> "CatMcpClient":
        """
        Get the most relevant MCP tools based on the user query using semantic similarity.

        Args:
            query_embeddings: The user query to find relevant tools for, expressed as a list of floats, i.e., the embedding vector.
            top_k: Number of top relevant tools to return

        Returns:
            Self for method chaining
        """
        if not query_embeddings:
            self._relevant_tools = self.mcp_tools[:top_k]
            return self

        # Ensure embeddings are cached (no-op if already cached)
        self._ensure_tool_embeddings_cached()

        # Get embeddings from the cache
        cache_key = self._get_cache_key()
        tool_embeddings = _MCP_TOOL_EMBEDDINGS_CACHE[cache_key]

        scores = []
        for item in tool_embeddings:
            tool_vec = item["embedding"]
            similarity = (
                    np.dot(query_embeddings, tool_vec) / (np.linalg.norm(query_embeddings) * np.linalg.norm(tool_vec))
            )
            scores.append(similarity)

        # Pick top K indices
        top_indices = np.argsort(scores)[-top_k:][::-1]
        self._relevant_tools = [tool_embeddings[i]["tool"] for i in top_indices]

        log.debug(f"MCP {self.name}: Selected {len(self._relevant_tools)} relevant tools.")
        return self

    def langchainfy(self) -> List[StructuredTool]:
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

        # Fallback to all tools if find_relevant_tools wasn't called
        source_tools = self._relevant_tools if self._relevant_tools else self.mcp_tools

        langchain_tools = []
        for mcp_tool in source_tools:
            # Use cached StructuredTool objects if we've created them before
            cache_key = f"{self.name}_{mcp_tool.name}"
            if cache_key in self._langchain_tools_cache:
                langchain_tools.append(self._langchain_tools_cache[cache_key])
                continue

            # Conversion logic
            try:
                description = mcp_tool.description or mcp_tool.name or "No description provided."
                if self.examples:
                    description += "\n\nE.g.:\n" + "\n".join(f"- {ex}" for ex in self.examples)

                structured_tool = StructuredTool.from_function(
                    name=cache_key,
                    description=description,
                    func=create_tool_caller(mcp_tool.name),
                    args_schema=mcp_tool.inputSchema,
                )

                self._langchain_tools_cache[cache_key] = structured_tool
                langchain_tools.append(structured_tool)
            except Exception as e:
                log.error(f"Failed converting {mcp_tool.name}: {e}")

        return langchain_tools

    def dictify_input_params(self) -> Dict:
        return {}

    @classmethod
    def reconstruct_from_params(cls, input_params: Dict) -> "CatProcedure":
        return cls()

    def __repr__(self) -> str:
        return f"CatMcpClient(name={self.name}, tools={len(self.mcp_tools)})"

    async def _get_mcp_tools_async(self) -> List[Tool]:
        """Asynchronously fetch MCP tools using a proper context manager."""
        async with self:
            return await self.list_tools()

    async def _get_mcp_prompts_async(self) -> List[Prompt]:
        """Asynchronously fetch MCP prompts using a proper context manager."""
        async with self:
            return await self.list_prompts()

    async def _get_mcp_resources_async(self) -> List[Resource]:
        """Asynchronously fetch MCP resources using a proper context manager."""
        async with self:
            return await self.list_resources()

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


def mcp_client(this_mcp_client: CatMcpClient) -> CatMcpClient:
    """Decorator for MCP client classes."""
    if this_mcp_client.name is None:
        this_mcp_client.name = this_mcp_client.__name__

    return this_mcp_client