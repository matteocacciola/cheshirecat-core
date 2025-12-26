from typing import Type
from pydantic import ConfigDict

from cat.core_plugins.factories.file_manager.custom import (
    AWSFileManager,
    AzureFileManager,
    GoogleCloudFileManager,
    LocalFileManager,
    DigitalOceanFileManager,
)
from cat.services.factory.file_manager import FileManagerConfig


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


class AWSFileManagerConfig(FileManagerConfig):
    bucket_name: str
    aws_access_key: str
    aws_secret_key: str

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "AWS API File Manager",
            "description": "Configuration for File Manager to be used with AWS S3 service",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[AWSFileManager]:
        return AWSFileManager


class AzureFileManagerConfig(FileManagerConfig):
    connection_string: str
    container_name: str

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Azure API File Manager",
            "description": "Configuration for File Manager to be used with Azure Blob service",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[AzureFileManager]:
        return AzureFileManager


class GoogleFileManagerConfig(FileManagerConfig):
    bucket_name: str
    credentials_path: str

    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Google Cloud API File Manager",
            "description": "Configuration for File Manager to be used with Google Cloud storage service",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[GoogleCloudFileManager]:
        return GoogleCloudFileManager


class DigitalOceanFileManagerConfig(AWSFileManagerConfig):
    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Digital Ocean API File Manager",
            "description": "Configuration for File Manager to be used with Digital Ocean Spaces service",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[DigitalOceanFileManager]:
        return DigitalOceanFileManager
