from typing import Type
from pydantic import ConfigDict
from cat.services.factory.file_manager import FileManagerConfig

from .custom import LocalFileManager


class LocalFileManagerConfig(FileManagerConfig):
    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Local API File Manager",
            "description": "Configuration for File Manager to be used to locally move files and directories",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[LocalFileManager]:
        return LocalFileManager
