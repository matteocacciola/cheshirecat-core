from datetime import datetime

from cat import tool


@tool(examples=["what time is it", "get the time"])
def get_the_time(cat):
    """Useful to get the current time when asked. Takes no input."""
    return f"The current time is {str(datetime.now())}"


@tool
def get_weather(city: str, when: str) -> str:
    """Get the weather for a given city and date."""
    return f"The weather in {city} on {when} is expected to be sunny."
