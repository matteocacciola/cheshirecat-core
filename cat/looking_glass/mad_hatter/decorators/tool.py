import importlib
import inspect
from typing import Callable, List, Dict
from langchain_core.documents import Document as LangChainDocument
from langchain_core.tools import StructuredTool
from fastmcp.tools.tool import ParsedFunction
from pydantic import ConfigDict
from slugify import slugify

from cat.looking_glass.mad_hatter.procedures import CatProcedure, CatProcedureType
from cat.services.memory.models import DocumentRecall


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
            validate=False,
        )

        return cls(
            func=func,
            name=parsed_function.name,
            description=parsed_function.description,
            input_schema=parsed_function.input_schema,
            output_schema=parsed_function.output_schema,
            examples=examples,
        )

    def to_document_recall(self) -> List[DocumentRecall]:
        triggers_map = {
            "description": [f"{self.name}: {self.description}"],
            "examples": self.examples,
        }

        return [
            DocumentRecall(
                document=LangChainDocument(
                    page_content=trigger_content,
                    metadata={
                        "obj_data": {
                            "__class__": self.__class__.__name__,
                            "__module__": self.__class__.__module__,
                            "input_params": {
                                "name": self.name,
                                "func": {
                                    "module": self.func.__module__,
                                    "name": self.func.__name__,
                                },
                                "description": self.description,
                                "input_schema": self.input_schema,
                                "output_schema": self.output_schema,
                                "examples": self.examples,
                            },
                        },
                        "source": self.name,
                        "type": str(self.type),
                        "trigger_type": trigger_type,
                    },
                ),
            )
            for trigger_type, trigger_list in triggers_map.items()
            for trigger_content in trigger_list
        ]

    @classmethod
    def reconstruct_from_params(cls, input_params: Dict) -> "CatTool":
        # Parse the function reference
        obj_module_path = input_params["func"]["module"]
        obj_name = input_params["func"]["name"]
        obj_module = importlib.import_module(obj_module_path)
        func = getattr(obj_module, obj_name, None)
        if not callable(func) and hasattr(func, "func"):
            func = func.func  # unwrap if it's a tool object

        # if func is still None, raise an error
        if func is None:
            raise ValueError(f"Function {obj_name} not found in module {obj_module_path}")

        # Create an instance with parsed params
        return cls(
            name=input_params["name"],
            func=func,
            description=input_params["description"],
            input_schema=input_params["input_schema"],
            output_schema=input_params["output_schema"],
            examples=input_params["examples"],
        )

    def _get_function(self) -> Callable:
        # create a closure to capture self.stray
        def func_with_cat(*args, **kwargs):
            sig = inspect.signature(original_func)
            valid_params = set(sig.parameters.keys())
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_params}
            filtered_kwargs["cat"] = stray
            return original_func(*args, **filtered_kwargs)

        # wrap func to inject the cat instance if func has the cat argument
        original_func = self.func
        if "cat" not in original_func.__code__.co_varnames or self.stray is None:
            return self.func

        stray = self.stray
        return func_with_cat

    def langchainfy(self) -> StructuredTool:
        """
        Convert CatProcedure to a langchain compatible StructuredTool object.

        Returns:
            The langchain compatible StructuredTool objects.
        """
        description = self.description + ("\n\nE.g.:\n" if self.examples else "")
        for example in self.examples:
            description += f"- {example}\n"

        return StructuredTool.from_function(
            name=self.name,
            description=description,
            func=self._get_function(),
            args_schema=self.input_schema,
        )

    @property
    def type(self) -> CatProcedureType:
        return CatProcedureType.TOOL

    @property
    def triggers_map(self) -> Dict[str, List[str]]:
        return {
            "description": [f"{self.name}: {self.description}"],
            "examples": self.examples,
        }

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
