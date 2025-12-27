import os
from io import BytesIO
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, Body
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cat.exceptions import CustomNotFoundException, CustomValidationException
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse
from cat.services.factory.file_manager import FileManagerAttributes
from cat.services.memory.utils import VectorMemoryType
from cat.services.service_factory import ServiceFactory

router = APIRouter(tags=["File Manager"], prefix="/file_manager")


class FileManagerDeletedFiles(BaseModel):
    deleted: bool


# get configured Plugin File Managers and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_file_managers_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the File Managers and their settings"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_file_managers",
        setting_category="file_manager",
        schema_name="fileManagerName",
    ).get_factory_settings(ccat.id)


@router.get("/settings/{file_manager_name}", response_model=GetSettingResponse)
async def get_file_manager_settings(
    file_manager_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified File Manager"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_file_managers",
        setting_category="file_manager",
        schema_name="fileManagerName",
    ).get_factory_setting(ccat.id, file_manager_name)


@router.put("/settings/{file_manager_name}", response_model=UpsertSettingResponse)
async def upsert_file_manager_setting(
    file_manager_name: str,
    payload: Dict = Body(default={}),
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.EDIT),
) -> UpsertSettingResponse:
    """Upsert the File Manager setting"""
    ccat = info.cheshire_cat

    result = ServiceFactory(
        ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_file_managers",
        setting_category="file_manager",
        schema_name="fileManagerName",
    ).upsert_service(ccat.agent_key, file_manager_name, payload)
    return UpsertSettingResponse(**result)


@router.get("/", response_model=FileManagerAttributes)
async def get_attributes(
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> FileManagerAttributes:
    ccat = info.cheshire_cat
    return ccat.file_manager.get_attributes(ccat.id)


@router.get("/files/{source_name}")
async def download_file(
    source_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> StreamingResponse:
    ccat = info.cheshire_cat

    # Security: Validate and sanitize the source parameter
    if not source_name or source_name.strip() == "":
        raise CustomValidationException("Invalid filename")

    # Remove any path separators and resolve path components
    # This prevents directory traversal attacks like "../../../etc/passwd"
    sanitized_source = os.path.basename(source_name.strip())

    # Additional validation: reject suspicious patterns
    forbidden_patterns = ['.', '..', '/', '\\', '\x00']
    if any(pattern in sanitized_source for pattern in forbidden_patterns):
        raise CustomValidationException("Invalid filename")

    # Validate filename characters (allow only alphanumeric, dash, underscore, dot)
    if not sanitized_source.replace('.', '').replace('-', '').replace('_', '').isalnum():
        raise CustomValidationException("Filename contains invalid characters")

    # Prevent hidden files and ensure reasonable length
    if sanitized_source.startswith('.') or len(sanitized_source) > 255:
        raise CustomValidationException("Invalid filename")

    # Optional: Additional path validation using pathlib for extra safety
    try:
        # This ensures the resolved path doesn't escape the intended directory
        base_path = Path(ccat.id).resolve()
        requested_path = (base_path / sanitized_source).resolve()

        # Ensure the resolved path is within the base directory
        if not str(requested_path).startswith(str(base_path)):
            raise CustomValidationException("Access denied")
    except (OSError, ValueError):
        raise CustomValidationException("Invalid file path")

    # Download the file
    file_content = ccat.file_manager.download(f"{ccat.id}/{sanitized_source}")
    if file_content is None:
        raise CustomNotFoundException("File not found")

    # Sanitize filename for Content-Disposition header to prevent header injection
    safe_filename = sanitized_source.encode("ascii", "ignore").decode("ascii")
    safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in ".-_")

    return StreamingResponse(
        BytesIO(file_content),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={safe_filename}"}
    )


@router.delete("/files/{source_name}")
async def delete_file(
    source_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> FileManagerDeletedFiles:
    """Delete a file"""
    ccat = info.cheshire_cat

    try:
        # delete the file from the file storage
        res = ccat.file_manager.remove_file_from_storage(f"{ccat.id}/{source_name}")

        # delete points
        collection_id = VectorMemoryType.DECLARATIVE
        metadata = {"source": source_name}
        await ccat.vector_memory_handler.delete_tenant_points_by_metadata_filter(str(collection_id), metadata)

        return FileManagerDeletedFiles(deleted=res)
    except Exception as e:
        raise CustomValidationException(f"Failed to delete memory points: {e}")


@router.delete("/files")
async def delete_files(
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> FileManagerDeletedFiles:
    """Delete all files"""
    ccat = info.cheshire_cat

    collection_id = VectorMemoryType.DECLARATIVE

    try:
        # get the list of files
        files = ccat.file_manager.get_attributes(ccat.id).files

        # delete all the files from the file storage
        res = ccat.file_manager.remove_folder_from_storage(ccat.id)

        # delete points
        for file in files:
            metadata = {"source": file.name}
            await ccat.vector_memory_handler.delete_tenant_points_by_metadata_filter(str(collection_id), metadata)

        return FileManagerDeletedFiles(deleted=res)
    except Exception as e:
        raise CustomValidationException(f"Failed to delete memory points: {e}")
