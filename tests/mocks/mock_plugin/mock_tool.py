import asyncio
from cat import tool


tool_examples = ["mock tool example 1", "mock tool example 2"]
tool_examples_async = ["mock tool async example 1", "mock tool async example 2"]


@tool(examples=tool_examples)
def mock_tool(topic, cat):
    """Used to test mock tools. Input is the topic."""

    return f"A mock about {topic} :)"


@tool(examples=tool_examples_async)
async def mock_tool_async(topic, cat):
    """Used to test async mock tools. Input is the topic."""

    # Simulate some async work
    await asyncio.sleep(0.1)
    return f"A mock about {topic} :)"
