import importlib
from abc import ABC, abstractmethod
from typing import List, Dict, Callable
from langchain_core.tools import StructuredTool
from pydantic import Field

from cat.services.memory.models import DocumentRecall
from cat.utils import Enum


class CatProcedureType(Enum):
    FORM = "form"
    TOOL = "tool"
    MCP = "mcp"


class CatProcedure(ABC):
    name: str
    func: Callable | None = None
    description: str | None = None
    input_schema: Dict = Field(default_factory=dict)
    output_schema: Dict = Field(default_factory=dict)
    examples: List[str] | None = Field(default_factory=list)
    plugin_id: str | None = None

    stray = None

    def inject_stray_cat(self, stray: "StrayCat") -> "CatProcedure":
        self.stray = stray
        return self

    @abstractmethod
    def to_document_recall(self) -> List[DocumentRecall]:
        """
        Convert CatProcedure into a list of DocumentRecall objects for memory storage.

        Returns:
            List[DocumentRecall]: List of DocumentRecall representing the procedure.
        """
        pass

    @classmethod
    def from_document_recall(cls, document: DocumentRecall, stray: "StrayCat") -> "CatProcedure":
        """
        Factory method to reconstruct a CatProcedure from stored metadata.
        Delegates to each subclass's own reconstruction logic.

        Args:
            document (DocumentRecall): DocumentRecall object containing metadata.
            stray (StrayCat): StrayCat instance.

        Returns:
            CatProcedure: Reconstructed CatProcedure instance.
        """
        obj_data = document.document.metadata["obj_data"]

        # Import the actual concrete class
        module = importlib.import_module(obj_data["__module__"])
        obj_class = getattr(module, obj_data["__class__"])

        # Delegate reconstruction to the subclass
        obj = obj_class.reconstruct_from_params(obj_data["input_params"])
        obj.inject_stray_cat(stray)

        return obj

    @classmethod
    @abstractmethod
    def reconstruct_from_params(cls, input_params: Dict) -> "CatProcedure":
        """
        Reconstructs an instance of CatProcedure from the given dictionary of input parameters.

        This class method serves as a factory method that initializes an instance of CatProcedure based on the provided
        parameters. It must be implemented by any subclass that inherits this method. The specific behavior, including
        how the dictionary is parsed or the object is constructed, depends on the implementation within each subclass.

        Args:
            input_params (Dict): A dictionary containing the input parameters required to reconstruct a CatProcedure instance.

        Returns:
            CatProcedure: A new instance of CatProcedure constructed using the given input parameters.
        """
        pass

    @abstractmethod
    def langchainfy(self) -> StructuredTool | None:
        """
        Provides an abstract method interface to define the `langchainfy` method for generating a `StructuredTool`
        instance.

        This method must be implemented in any subclass and is designed to facilitate the creation and retrieval of a
        `StructuredTool` object in a structured manner.

        Returns:
            StructuredTool: The `StructuredTool` instance, or None if the procedure cannot be converted to a
                `StructuredTool`.
        """
        pass

    @property
    @abstractmethod
    def type(self) -> CatProcedureType:
        pass
