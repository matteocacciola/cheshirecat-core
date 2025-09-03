import functools
import inspect
from typing import Callable, List
from langchain_core.tools import StructuredTool
from pydantic import ConfigDict


# All @tool decorated functions in plugins become a CatTool.
# The difference between base langchain Tool and CatTool is that CatTool has an instance of the cat as attribute
# (set by the plugin manager)
class CatTool:
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
        self.procedure_type = "tool"
        self.name = name
        self.description = description
        self.return_direct = return_direct

        self.triggers_map = {
            "description": [f"{name}: {description}"],
            "start_example": examples,
        }
        # remove cat argument from signature so it does not end up in prompts
        self.signature = f"{inspect.signature(self.func)}".replace(", cat)", ")")

    @property
    def start_examples(self):
        return self.triggers_map["start_example"]

    def __repr__(self) -> str:
        return f"CatTool(name={self.name}, return_direct={self.return_direct}, description={self.description})"

    def run(self, input_by_llm: str, stray: "StrayCat") -> str:
        return self.func(input_by_llm, cat=stray)

    async def arun(self, input_by_llm: dict, stray: "StrayCat") -> str:
        return self.func(input_by_llm, cat=stray)

    def execute(self, stray: "StrayCat", action: "LLMAction") -> "LLMAction":
        """
        Execute a CatTool with the provided LLMAction.
        Will store tool output in action.output.

        Parameters
        ----------
        action: LLMAction
            Object representing the choice of tool made by the LLM
        stray: StrayCat
            Session object.

        Returns
        -------
        LLMAction
            Updated LLM action, with valued output.
        """
        if action.input is None:
            action.input = {}
        tool_output = self.func(**action.input, cat=stray)

        # Ensure the output is a string or None,
        if tool_output is not None and not isinstance(tool_output, str):
            tool_output = str(tool_output)

        # store tool output
        action.output = tool_output

        # TODO: should return something analogous to:
        #   https://modelcontextprotocol.info/specification/2024-11-05/server/tools/#tool-result
        #   Only supporting text for now
        return action

    def _remove_cat_from_args(self, function: Callable) -> Callable:
        """
        Remove 'cat' and '_' parameters from function signature for LangChain compatibility.

        Parameters
        ----------
        function : Callable
            The function to modify.

        Returns
        -------
        Callable
            The modified function without 'cat' and '_' parameters.
        """
        signature = inspect.signature(function)
        parameters = list(signature.parameters.values())

        filtered_parameters = [p for p in parameters if p.name != 'cat' and p.name != '_']
        new_signature = signature.replace(parameters=filtered_parameters)

        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            if "cat" in kwargs:
                del kwargs["cat"]
            return function(*args, **kwargs)

        wrapper.__signature__ = new_signature
        return wrapper

    def langchainfy(self):
        """Convert CatTool to a langchain compatible StructuredTool object"""
        if getattr(self, "arg_schema", None) is not None:
            return StructuredTool(
                name=self.name.strip().replace(" ", "_"),
                description=self.description,
                func=self._remove_cat_from_args(self.func),
                args_schema=getattr(self, "arg_schema"),
            )

        return StructuredTool.from_function(
            name=self.name.strip().replace(" ", "_"),
            description=self.description,
            func=self._remove_cat_from_args(self.func),
        )


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
