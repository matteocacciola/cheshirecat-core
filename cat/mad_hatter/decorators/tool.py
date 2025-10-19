from typing import Callable, List, Dict
from langchain_core.tools import StructuredTool
from fastmcp.tools.tool import ParsedFunction
from mcp.types import Tool
from pydantic import ConfigDict
from slugify import slugify

from cat.mad_hatter.procedures import CatProcedure, CatProcedureType


class CatTool(CatProcedure):
    model_config = ConfigDict(extra="allow")

    def __init__(
        self,
        name: str,
        func: Callable,
        description: str | None = None,
        input_schema: Dict | None = None,
        output_schema: Dict | None = None,
        examples: List[str] | None = None,
    ):
        self.name = slugify(name.strip(), separator="_")
        self.func = func
        self.description = description if description else (func.__doc__.strip() if func.__doc__ else "")
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.examples = examples or []

    def __repr__(self) -> str:
        return f"CatTool(name={self.name}, description={self.description})"

    @classmethod
    def from_decorated_function(
        cls,
        func: Callable,
        examples: List[str] | None = None,
    ) -> "CatTool":
        examples = examples or []
        parsed_function = ParsedFunction.from_function(
            func,
            exclude_args=["cat"],  # awesome, will only be used at execution
            validate=False
        )

        return cls(
            func=func,
            name=parsed_function.name,
            description=parsed_function.description,
            input_schema=parsed_function.input_schema,
            output_schema=parsed_function.output_schema,
            examples=examples,
        )

    @classmethod
    def from_fastmcp(
        cls,
        t: Tool,
        mcp_client_func: Callable
    ) -> "CatTool":
        return cls(
            func=mcp_client_func,
            name=t.name,
            description=t.description or t.name,
            input_schema=t.inputSchema,
            output_schema=t.outputSchema,
        )

    def langchainfy(self) -> List[StructuredTool]:
        """
        Convert CatProcedure to a langchain compatible StructuredTool object.

        Returns
        -------
        List[StructuredTool]
            The langchain compatible StructuredTool objects.
        """
        description = self.description + ("\n\nE.g.:\n" if self.examples else "")
        for example in self.examples:
            description += f"- {example}\n"

        # wrap func to inject cat instance if func has cat argument
        func: Callable = self.func
        if "cat" in func.__code__.co_varnames and self.stray is not None:
            # create a closure to capture self.stray
            def func_with_cat(*args, **kwargs):
                return func(*args, cat=self.stray, **kwargs)
            func = func_with_cat

        return [StructuredTool.from_function(
            name=self.name,
            description=description,
            func=func,
            args_schema=self.input_schema,
        )]

    @property
    def type(self) -> CatProcedureType:
        return CatProcedureType.TOOL


def tool(
    *args: str | Callable, examples: List[str] | None = None
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

    def decorator() -> Callable:
        def _make_tool(func: Callable[[str], str]) -> CatTool:
            assert func.__doc__, "Function must have a docstring"
            tool_ = CatTool.from_decorated_function(func, examples=examples)
            return tool_

        return _make_tool

    # example usages: @tool("search") or @tool with a function as argument (e.g. @tool(func))
    if len(args) == 1:
        return decorator()(args[0]) if callable(args[0]) else decorator()

    # if there are no arguments; example usage: @tool
    if len(args) == 0:
        def _partial(func: Callable[[str], str]) -> CatTool:
            return decorator()(func)

        return _partial

    raise ValueError("Too many arguments for tool decorator")
