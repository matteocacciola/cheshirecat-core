import inspect
from typing import Callable, List, Dict
from pydantic import ConfigDict

from cat.mad_hatter.procedures import CatProcedure
from cat.utils import run_sync_or_async


# All @tool decorated functions in plugins become a CatTool.
# The difference between base langchain Tool and CatTool is that CatTool has an instance of the cat as attribute
# (set by the plugin manager)
class CatTool(CatProcedure):
    model_config = ConfigDict(extra="allow")

    def __init__(
        self,
        name: str,
        func: Callable,
        return_direct: bool = False,
        examples: List[str] = None,
    ):
        examples = examples or []
        description = func.__doc__.strip() if func.__doc__ else ""

        self.func = func
        self.name = name
        self.description = description
        self._return_direct = return_direct

        self.triggers_map = {
            "description": [f"{name}: {description}"],
            "start_example": examples,
        }
        # remove cat argument from signature so it does not end up in prompts
        self.signature = f"{inspect.signature(self.func)}".replace(", cat)", ")")

    @property
    def start_examples(self):
        return self.triggers_map["start_example"]

    @property
    def procedure_type(self) -> str:
        return "tool"

    @property
    def return_direct(self) -> bool:
        return self._return_direct

    def __repr__(self) -> str:
        return f"CatTool(name={self.name}, return_direct={self.return_direct}, description={self.description})"

    def run(self, input_by_llm: str, stray: "StrayCat") -> str:
        return self.func(input_by_llm, cat=stray)

    async def arun(self, input_by_llm: dict, stray: "StrayCat") -> str:
        return self.func(input_by_llm, cat=stray)

    async def execute(self, stray: "StrayCat", tool_call: Dict) -> str:
        """
        Execute a CatTool with the provided LLMAction.
        Will store tool output in action.output.

        Parameters
        ----------
        tool_call: Dict
            LLMAction object containing the tool call information.
        stray: StrayCat
            Session object.

        Returns
        -------
        str
            The output of the tool execution.
        """
        tool_output = await run_sync_or_async(self.func, **tool_call["args"], cat=stray)

        # Ensure the output is a string or None,
        if tool_output is not None and not isinstance(tool_output, str):
            tool_output = str(tool_output)

        # TODO: should return something analogous to:
        #   https://modelcontextprotocol.info/specification/2024-11-05/server/tools/#tool-result
        #   Only supporting text for now
        return tool_output


# @tool decorator, a modified version of a langchain Tool that also takes a Cat instance as argument
# adapted from https://github.com/hwchase17/langchain/blob/master/langchain/agents/tools.py
def tool(
    *args: str | Callable, return_direct: bool = False, examples: List[str] = None
) -> Callable:
    """
    Make tools out of functions, can be used with or without arguments.
    Requires:
        - Function must contain the cat argument -> str
        - Function must have a docstring
    Examples:
        .. code-block:: python
            @tool
            def search_api(query: str, cat) -> str:
                # Searches the API for the query.
                return "https://api.com/search?q=" + query
            @tool("search", return_direct=True)
            def search_api(query: str, cat) -> str:
                # Searches the API for the query.
                return "https://api.com/search?q=" + query
    """
    examples = examples or []

    def _make_with_name(tool_name: str) -> Callable:
        def _make_tool(func: Callable[[str], str]) -> CatTool:
            assert func.__doc__, "Function must have a docstring"
            tool_ = CatTool(
                name=tool_name,
                func=func,
                return_direct=return_direct,
                examples=examples,
            )
            return tool_

        return _make_tool

    if len(args) == 1 and isinstance(args[0], str):
        # if the argument is a string, then we use the string as the tool name
        # Example usage: @tool("search", return_direct=True)
        return _make_with_name(args[0])
    if len(args) == 1 and callable(args[0]):
        # if the argument is a function, then we use the function name as the tool name
        # Example usage: @tool
        return _make_with_name(args[0].__name__)(args[0])
    if len(args) == 0:
        # if there are no arguments, then we use the function name as the tool name
        # Example usage: @tool(return_direct=True)
        def _partial(func: Callable[[str], str]) -> CatTool:
            return _make_with_name(func.__name__)(func)

        return _partial

    raise ValueError("Too many arguments for tool decorator")
