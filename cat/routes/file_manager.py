import os
from io import BytesIO
from pathlib import Path
from typing import Dict, List
from fastapi import APIRouter, Body
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cat.exceptions import CustomNotFoundException, CustomValidationException
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse
from cat.services.factory.file_manager import FileResponse
from cat.services.memory.models import VectorMemoryType
from cat.services.service_factory import ServiceFactory

router = APIRouter(tags=["File Manager"], prefix="/file_manager")


class FileManagerDeletedFiles(BaseModel):
    deleted: bool


class FileManagerAttributes(BaseModel):
    files: List[FileResponse]
    size: int


# get configured Plugin File Managers and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_file_managers_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.READ),
) -> GetSettingsResponse:
    """Get the list of the File Managers and their settings"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        agent_key=ccat.agent_key,
        hook_manager=ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_file_managers",
        setting_category="file_manager",
        schema_name="fileManagerName",
    ).get_factory_settings()


@router.get("/settings/{file_manager_name}", response_model=GetSettingResponse)
async def get_file_manager_settings(
    file_manager_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified File Manager"""
    ccat = info.cheshire_cat
    return ServiceFactory(
        agent_key=ccat.agent_key,
        hook_manager=ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_file_managers",
        setting_category="file_manager",
        schema_name="fileManagerName",
    ).get_factory_setting(file_manager_name)


@router.put("/settings/{file_manager_name}", response_model=UpsertSettingResponse)
async def upsert_file_manager_setting(
    file_manager_name: str,
    payload: Dict = Body(default={}),
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.WRITE),
) -> UpsertSettingResponse:
    """Upsert the File Manager setting"""
    ccat = info.cheshire_cat

    result = ServiceFactory(
        agent_key=ccat.agent_key,
        hook_manager=ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_file_managers",
        setting_category="file_manager",
        schema_name="fileManagerName",
    ).upsert_service(file_manager_name, payload)
    return UpsertSettingResponse(**result)


@router.get("/", response_model=FileManagerAttributes)
async def get_attributes(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> FileManagerAttributes:
    ccat = info.cheshire_cat

    list_files = ccat.file_manager.list_files(ccat.id)
    return FileManagerAttributes(files=list_files, size=sum(file.size for file in list_files))


@router.get("/files/{source_name}")
async def download_file(
    source_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> StreamingResponse:
    ccat = info.cheshire_cat

    # Security: Validate and sanitize the source parameter
    if not source_name or source_name.strip() == "":
        raise CustomValidationException("Invalid filename")

    # Remove any path separators and resolve path components
    # This prevents directory traversal attacks like "../../../etc/passwd"
    sanitized_source = os.path.basename(source_name.strip())
    sanitized_source, sanitized_extension = os.path.splitext(sanitized_source)

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
    sanitized_source = f"{sanitized_source}{sanitized_extension}"
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
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> FileManagerDeletedFiles:
    """Delete a file"""
    ccat = info.cheshire_cat

    try:
        # delete the file from the file storage
        res = ccat.file_manager.remove_file_from_storage(f"{ccat.id}/{source_name}")

        # delete points
        collection_id = VectorMemoryType.DECLARATIVE
        metadata = {"source": source_name}
        await ccat.vector_memory_handler.delete_tenant_points(str(collection_id), metadata)

        return FileManagerDeletedFiles(deleted=res)
    except Exception as e:
        raise CustomValidationException(f"Failed to delete memory points: {e}")


@router.delete("/files")
async def delete_files(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> FileManagerDeletedFiles:
    """Delete all files"""
    ccat = info.cheshire_cat

    collection_id = VectorMemoryType.DECLARATIVE

    try:
        # get the list of files
        files = ccat.file_manager.list_files(ccat.id)

        # delete all the files from the file storage
        res = ccat.file_manager.remove_folder_from_storage(ccat.id)

        # delete points
        for file in files:
            metadata = {"source": file.name}
            await ccat.vector_memory_handler.delete_tenant_points(str(collection_id), metadata)

        return FileManagerDeletedFiles(deleted=res)
    except Exception as e:
        raise CustomValidationException(f"Failed to delete memory points: {e}")
