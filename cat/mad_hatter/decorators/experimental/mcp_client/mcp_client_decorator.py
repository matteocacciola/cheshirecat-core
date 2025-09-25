from .cat_mcp_client import CatMcpClient


# mcp_client decorator
def mcp_client(this_mcp_client: CatMcpClient) -> CatMcpClient:
    if this_mcp_client.name is None:
        this_mcp_client.name = this_mcp_client.__name__

    return this_mcp_client
