import os
from io import BytesIO
from typing import Dict, List, Tuple
from fastapi import APIRouter, Body, BackgroundTasks
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthResource, AuthPermission, check_permissions
from cat.exceptions import CustomNotFoundException, CustomValidationException
from cat.routes.routes_utils import GetSettingsResponse, GetSettingResponse, UpsertSettingResponse, sanitize_source_name
from cat.services.factory.file_manager import FileResponse
from cat.services.memory.models import VectorMemoryType
from cat.services.service_factory import ServiceFactory

router = APIRouter(tags=["File Manager"], prefix="/file_manager")


class FileManagerDeletedFiles(BaseModel):
    deleted: bool


class FileManagerAttributes(BaseModel):
    files: List[FileResponse]
    size: int


def get_from_info(info: AuthorizedInfo) -> Tuple[str, VectorMemoryType, Dict]:
    ccat = info.cheshire_cat
    path = ccat.agent_key
    if info.stray_cat:
        path = os.path.join(path, info.stray_cat.id)

    collection_id = VectorMemoryType.DECLARATIVE if not info.stray_cat else VectorMemoryType.EPISODIC
    metadata = {"chat_id": info.stray_cat.id} if info.stray_cat else {}

    return path, collection_id, metadata


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
    background_tasks: BackgroundTasks,
    file_manager_name: str,
    payload: Dict = Body(default={}),
    info: AuthorizedInfo = check_permissions(AuthResource.FILE_MANAGER, AuthPermission.WRITE),
) -> UpsertSettingResponse:
    """Upsert the File Manager setting"""
    ccat = info.cheshire_cat

    previous_file_manager = ccat.file_manager

    result = ServiceFactory(
        agent_key=ccat.agent_key,
        hook_manager=ccat.plugin_manager,
        factory_allowed_handler_name="factory_allowed_file_managers",
        setting_category="file_manager",
        schema_name="fileManagerName",
    ).upsert_service(file_manager_name, payload)

    current_file_manager = ccat.file_manager
    if previous_file_manager != current_file_manager:
        background_tasks.add_task(ccat.transfer_files_from, previous_file_manager)

    return UpsertSettingResponse(**result)


@router.get("/", response_model=FileManagerAttributes)
async def get_attributes(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> FileManagerAttributes:
    path, _, _ = get_from_info(info)

    list_files = info.cheshire_cat.file_manager.list_files(path)
    return FileManagerAttributes(files=list_files, size=sum(file.size for file in list_files))


@router.get("/files/{source_name:path}")
async def download_file(
    source_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> StreamingResponse:
    path, _, _ = get_from_info(info)

    sanitized_source = sanitize_source_name(source_name, path=path)

    # Download the file
    file_content = info.cheshire_cat.file_manager.download_file(os.path.join(path, sanitized_source))
    if file_content is None:
        raise CustomNotFoundException("File not found")

    # Sanitize the filename for the Content-Disposition header to prevent header injection
    safe_filename = sanitized_source.encode("ascii", "ignore").decode("ascii")
    safe_filename = "".join(c for c in safe_filename if c.isalnum() or c in ".-_")

    return StreamingResponse(
        BytesIO(file_content),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={safe_filename}"}
    )


@router.delete("/files/{source_name:path}")
async def delete_file(
    source_name: str,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> FileManagerDeletedFiles:
    """Delete a file"""
    path, collection_id, metadata = get_from_info(info)
    metadata = {"source": source_name} | metadata

    sanitized_source = sanitize_source_name(source_name, path=path)

    try:
        # delete the file from the file storage
        res = info.cheshire_cat.file_manager.remove_file(os.path.join(path, sanitized_source))

        # delete points
        await info.cheshire_cat.vector_memory_handler.delete_tenant_points(str(collection_id), metadata)

        return FileManagerDeletedFiles(deleted=res)
    except Exception as e:
        raise CustomValidationException(f"Failed to delete memory points: {e}")


@router.delete("/files")
async def delete_files(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> FileManagerDeletedFiles:
    """Delete all files"""
    path, collection_id, metadata = get_from_info(info)

    try:
        # get the list of files
        files = info.cheshire_cat.file_manager.list_files(path)

        # delete all the files from the file storage
        res = info.cheshire_cat.file_manager.remove_folder(path)

        # delete points
        for file in files:
            metadata |= {"source": file.name}
            await info.cheshire_cat.vector_memory_handler.delete_tenant_points(str(collection_id), metadata)

        return FileManagerDeletedFiles(deleted=res)
    except Exception as e:
        raise CustomValidationException(f"Failed to delete memory points: {e}")
