import os
from io import BytesIO
from pathlib import Path
from typing import Dict
from fastapi import APIRouter, Body
from starlette.responses import StreamingResponse

from cheshirecat.auth.connection import AuthorizedInfo
from cheshirecat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cheshirecat.exceptions import CustomNotFoundException, CustomValidationException
from cheshirecat.factory.file_manager import FileManagerFactory, FileManagerAttributes
from cheshirecat.routes.routes_utils import (
    GetSettingsResponse,
    GetSettingResponse,
    UpsertSettingResponse,
    get_factory_settings,
    get_factory_setting,
    on_upsert_factory_setting,
)

router = APIRouter()


# get configured Plugin File Managers and configuration schemas
@router.get("/settings", response_model=GetSettingsResponse)
async def get_file_managers_settings(
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> GetSettingsResponse:
    """Get the list of the File Managers and their settings"""
    ccat = info.cheshire_cat
    return get_factory_settings(ccat.id, FileManagerFactory(ccat.plugin_manager))


@router.get("/settings/{file_manager_name}", response_model=GetSettingResponse)
async def get_file_manager_settings(
    file_manager_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.READ),
) -> GetSettingResponse:
    """Get settings and scheme of the specified File Manager"""
    ccat = info.cheshire_cat
    factory = FileManagerFactory(ccat.plugin_manager)
    return get_factory_setting(ccat.id, file_manager_name, factory)


@router.put("/settings/{file_manager_name}", response_model=UpsertSettingResponse)
async def upsert_file_manager_setting(
    file_manager_name: str,
    payload: Dict = Body(...),
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.EDIT),
) -> UpsertSettingResponse:
    """Upsert the File Manager setting"""
    ccat = info.cheshire_cat
    on_upsert_factory_setting(file_manager_name, FileManagerFactory(ccat.plugin_manager))

    return UpsertSettingResponse(**ccat.replace_file_manager(file_manager_name, payload).model_dump())


@router.get("/", response_model=FileManagerAttributes)
async def get_attributes(
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> FileManagerAttributes:
    ccat = info.cheshire_cat
    return ccat.file_manager.get_attributes(ccat.id)


@router.get("/download/{source}")
async def download(
    source: str,
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.LIST),
) -> StreamingResponse:
    ccat = info.cheshire_cat

    # Security: Validate and sanitize the source parameter
    if not source or source.strip() == "":
        raise CustomValidationException("Invalid filename")

    # Remove any path separators and resolve path components
    # This prevents directory traversal attacks like "../../../etc/passwd"
    sanitized_source = os.path.basename(source.strip())

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
