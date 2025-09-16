from typing import Callable, List
from langchain_core.tools import StructuredTool
from pydantic import ConfigDict

from cat.mad_hatter.procedures import CatProcedure


# All @tool decorated functions in plugins become a CatTool.
# The difference between base langchain Tool and CatTool is that CatTool has an instance of the cat as attribute
class CatTool(CatProcedure):
    model_config = ConfigDict(extra="allow")

    def __init__(
        self,
        name: str,
        func: Callable,
        examples: List[str] = None,
    ):
        self.name = name
        self.description = func.__doc__.strip() if func.__doc__ else ""
        self.start_examples = examples or []
        self.func = func
        self._stray = None

    def __repr__(self) -> str:
        return f"CatTool(name={self.name}, description={self.description})"

    def inject_cat(self, cat) -> None:
        self._stray = cat

    def langchainfy(self) -> List[StructuredTool]:
        """
        Convert CatProcedure to a langchain compatible StructuredTool object.

        Returns
        -------
        List[StructuredTool]
            The langchain compatible StructuredTool objects.
        """
        description = self.description + ("\n\nE.g.:\n" if self.start_examples else "")
        for example in self.start_examples:
            description += f"- {example}\n"

        # wrap func to inject cat instance if func has cat argument
        func: Callable = self.func
        if "cat" in func.__code__.co_varnames:
            def func_with_cat(*args, **kwargs):
                return func(*args, cat=self._stray, **kwargs)
            func = func_with_cat

        if getattr(self, "arg_schema", None) is not None:
            return [StructuredTool(
                name=self.name.strip().replace(" ", "_"),
                description=description,
                func=func,
                args_schema=getattr(self, "arg_schema"),
            )]

        return [StructuredTool.from_function(
            name=self.name.strip().replace(" ", "_"),
            description=description,
            func=func,
        )]


# @tool decorator, a modified version of a langchain Tool that also takes a Cat instance as argument
# adapted from https://github.com/hwchase17/langchain/blob/master/langchain/agents/tools.py
def tool(
    *args: str | Callable, examples: List[str] = None
) -> Callable:
    """
    Make tools out of functions, can be used with or without arguments.
    Requires:
        - Function must have a docstring
    Examples:
        .. code-block:: python
            @tool
            def search_api(query: str) -> str:
                # Searches the API for the query.
                return "https://api.com/search?q=" + query
            @tool("search")
            def search_api(query: str) -> str:
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
                examples=examples,
            )
            return tool_

        return _make_tool

    if len(args) == 1 and isinstance(args[0], str):
        # if the argument is a string, then we use the string as the tool name
        # Example usage: @tool("search")
        return _make_with_name(args[0])
    if len(args) == 1 and callable(args[0]):
        # if the argument is a function, then we use the function name as the tool name
        # Example usage: @tool
        return _make_with_name(args[0].__name__)(args[0])
    if len(args) == 0:
        # if there are no arguments, then we use the function name as the tool name
        # Example usage: @tool
        def _partial(func: Callable[[str], str]) -> CatTool:
            return _make_with_name(func.__name__)(func)

        return _partial

    raise ValueError("Too many arguments for tool decorator")
