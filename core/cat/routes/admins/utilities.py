from typing import List
from fastapi import APIRouter, Request
from pydantic import BaseModel

from cat.auth.auth_utils import extract_agent_id_from_request
from cat.auth.permissions import AdminAuthResource, AuthPermission, check_admin_permissions
from cat.db import crud
from cat.db.database import get_db
from cat.log import log
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.routes.routes_utils import startup_app, shutdown_app
from cat.utils import empty_plugin_folder

router = APIRouter()

class ResetResponse(BaseModel):
    deleted_settings: bool
    deleted_memories: bool
    deleted_plugin_folders: bool


class CreatedResponse(BaseModel):
    created: bool


@router.post("/factory/reset", response_model=ResetResponse)
async def factory_reset(
    request: Request,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE),
) -> ResetResponse:
    """
    Factory reset the entire application. This will delete all settings, memories, and metadata.
    """

    await shutdown_app(request.app)

    try:
        get_db().flushdb()
        deleted_settings = True
    except Exception as e:
        log.error(f"Error deleting settings: {e}")
        deleted_settings = False

    try:
        empty_plugin_folder()
        deleted_plugin_folders = True
    except Exception as e:
        log.error(f"Error deleting plugin folders: {e}")
        deleted_plugin_folders = False

    await startup_app(request.app)

    return ResetResponse(
        deleted_settings=deleted_settings,
        deleted_memories=False,
        deleted_plugin_folders=deleted_plugin_folders,
    )


@router.get("/agents", dependencies=[check_admin_permissions(AdminAuthResource.CHESHIRE_CATS, AuthPermission.LIST)])
async def get_agents() -> List[str]:
    """
    Get all agents.
    """

    try:
        return sorted(crud.get_agents_main_keys())
    except Exception as e:
        log.error(f"Error creating agent: {e}")
        return []


@router.post("/agent/create", response_model=CreatedResponse)
async def agent_create(
    request: Request,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE),
) -> CreatedResponse:
    """
    Reset a single agent. This will delete all settings, memories, and metadata, for the agent.
    """

    try:
        agent_id = extract_agent_id_from_request(request)
        await lizard.create_cheshire_cat(agent_id)

        return CreatedResponse(created=True)
    except Exception as e:
        log.error(f"Error creating agent: {e}")
        return CreatedResponse(created=False)


@router.post("/agent/destroy", response_model=ResetResponse)
async def agent_destroy(
    request: Request,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE),
) -> ResetResponse:
    """
    Destroy a single agent. This will completely delete all settings, memories, and metadata, for the agent.
    This is a permanent action and cannot be undone.
    """

    agent_id = extract_agent_id_from_request(request)
    ccat = lizard.get_cheshire_cat_from_db(agent_id)
    if not ccat:
        return ResetResponse(deleted_settings=False, deleted_memories=False, deleted_plugin_folders=False)

    try:
        await ccat.destroy()
        deleted_settings = True
        deleted_memories = True
    except Exception as e:
        log.error(f"Error deleting settings: {e}")
        deleted_settings = False
        deleted_memories = False

    return ResetResponse(
        deleted_settings=deleted_settings,
        deleted_memories=deleted_memories,
        deleted_plugin_folders=False,
    )


@router.post("/agent/reset", response_model=ResetResponse)
async def agent_reset(
    request: Request,
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.CHESHIRE_CATS, AuthPermission.DELETE),
) -> ResetResponse:
    """
    Reset a single agent. This will delete all settings, memories, and metadata, for the agent.
    """

    result = await agent_destroy(request, lizard)

    agent_id = extract_agent_id_from_request(request)
    await lizard.create_cheshire_cat(agent_id)

    return result
