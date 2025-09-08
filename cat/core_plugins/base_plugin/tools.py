from datetime import datetime

from cat.mad_hatter.decorators import tool


@tool(examples=["what time is it", "get the time"])
def get_the_time():
    """Useful to get the current time when asked. Input is always None."""
    return f"The current time is {str(datetime.now())}"


@tool
def get_weather(city: str, when: str) -> str:
    """Get the weather for a given city and date."""
    return f"The weather in {city} on {when} is expected to be sunny."
