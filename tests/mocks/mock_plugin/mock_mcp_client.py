from datetime import datetime
from typing import Dict, Any, List
from fastmcp import FastMCP

from cat.mad_hatter.decorators import CatMcpClient, mcp_client

# Create in memory server for testing, otherwise tests get slow
server = FastMCP("TestInMemoryServer")

@server.tool
async def add(a: int, b: int) -> int:
    return a + b

@server.tool
async def get_the_time() -> str:
    return str(datetime.now())

@server.tool
async def get_the_timezone(city) -> str:
    return f"Time in {city} is {datetime.now()}"

@server.prompt
def explain_topic(topic: str, language: str) -> str:
    return f"Can you explain {topic} in {language}?"

@server.resource("resource://welcome-message")
def get_resource() -> str:
    return "This is a welcoming resource"


# now, create a mock client using the above server
@mcp_client
class MockMcpClient(CatMcpClient):
    """
    Mock MCP Client for testing purposes.
    """
    name = "mock_mcp_client"
    description = "Mock MCP Client for testing"

    @property
    def init_args(self) -> List | Dict[str, Any]:
        return [server]
