from datetime import datetime

from cat.mad_hatter.decorators import tool


@tool(examples=["what time is it", "get the time"])
def get_the_time(cat):
    """Useful to get the current time when asked. Input is always None."""
    return f"The current time is {str(datetime.now())}"


@tool(examples=["log working memory", "show me the contents of working memory"])
def read_working_memory(cat):
    """Get the content of the Working Memory."""
    return str(cat.working_memory)


@tool
def get_weather(city: str, when: str, cat) -> str:
    """Get the weather for a given city and date."""
    return f"The weather in {city} on {when} is expected to be sunny."
