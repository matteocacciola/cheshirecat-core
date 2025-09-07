from abc import ABC
import functools
import inspect
from typing import Callable

from langchain_core.tools import StructuredTool


class CatProcedure(ABC):
    name: str
    description: str
    func: Callable

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

        filtered_parameters = [p for p in parameters if p.name != "cat" and p.name != "_"]
        new_signature = signature.replace(parameters=filtered_parameters)

        @functools.wraps(function)
        def wrapper(*args, **kwargs):
            if "cat" in kwargs:
                del kwargs["cat"]
            return function(*args, **kwargs)

        wrapper.__signature__ = new_signature
        return wrapper

    def langchainfy(self) -> StructuredTool:
        """
        Convert CatProcedure to a langchain compatible StructuredTool object.

        Returns
        -------
        StructuredTool
            The langchain compatible StructuredTool object.
        """
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
