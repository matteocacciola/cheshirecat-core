import os
import shutil
from typing import List
from fastapi import APIRouter, Request
from pydantic import BaseModel

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.db import crud
from cat.db.database import get_db
from cat.log import log
from cat.memory.utils import VectorMemoryType
from cat.routes.routes_utils import startup_app, shutdown_app
from cat.utils import get_plugins_path

router = APIRouter(tags=["Utilities"], prefix="/utils")


class ResetResponse(BaseModel):
    deleted_settings: bool
    deleted_memories: bool
    deleted_plugin_folders: bool


class CreatedResponse(BaseModel):
    created: bool


class AgentRequest(BaseModel):
    agent_id: str


class AgentClonedResponse(BaseModel):
    cloned: bool = False


@router.post("/factory/reset", response_model=ResetResponse)
async def factory_reset(
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.ADMIN, AuthPermission.DESTROY),
) -> ResetResponse:
    """
    Factory reset the entire application. This will delete all settings, memories, and metadata.
    """
    # remove memories
    cheshire_cats_ids = crud.get_agents_main_keys()
    deleted_memories = False
    for agent_id in cheshire_cats_ids:
        ccat = info.lizard.get_cheshire_cat_from_db(agent_id)
        if not ccat:
            continue
        try:
            await ccat.destroy()
            deleted_memories = True
        except Exception as e:
            log.error(f"Error deleting memories for agent {agent_id}: {e}")
            deleted_memories = False

    await shutdown_app(request.app)

    try:
        get_db().flushdb()
        deleted_settings = True
    except Exception as e:
        log.error(f"Error deleting settings: {e}")
        deleted_settings = False

    try:
        # empty the plugin folder
        plugin_folder = get_plugins_path()
        for _, folders, _ in os.walk(plugin_folder):
            for folder in folders:
                item = os.path.join(plugin_folder, folder)
                if os.path.isfile(item) or not os.path.exists(item):
                    continue
                shutil.rmtree(item)

        deleted_plugin_folders = True
    except Exception as e:
        log.error(f"Error deleting plugin folders: {e}")
        deleted_plugin_folders = False

    await startup_app(request.app)

    return ResetResponse(
        deleted_settings=deleted_settings,
        deleted_memories=deleted_memories,
        deleted_plugin_folders=deleted_plugin_folders,
    )


@router.get("/agents", dependencies=[check_permissions(AuthResource.CHESHIRE_CAT, AuthPermission.LIST)])
async def get_agents() -> List[str]:
    """
    Get all agents.
    """
    try:
        return sorted(crud.get_agents_main_keys())
    except Exception as e:
        log.error(f"Error creating agent: {e}")
        return []


@router.post("/agents/create", response_model=CreatedResponse)
async def agent_create(
    request: AgentRequest,
    info: AuthorizedInfo = check_permissions(AuthResource.CHESHIRE_CAT, AuthPermission.WRITE),
) -> CreatedResponse:
    """
    Reset a single agent. This will delete all settings, memories, and metadata, for the agent.
    """
    try:
        await info.lizard.create_cheshire_cat(request.agent_id)
        return CreatedResponse(created=True)
    except Exception as e:
        log.error(f"Error creating agent: {e}")
        return CreatedResponse(created=False)


@router.post("/agents/destroy", response_model=ResetResponse)
async def agent_destroy(
    request: Request,
    info: AuthorizedInfo = check_permissions(AuthResource.CHESHIRE_CAT, AuthPermission.DELETE),
) -> ResetResponse:
    """
    Destroy a single agent. This will completely delete all settings, memories, and metadata, for the agent.
    This is a permanent action and cannot be undone.
    """
    deleted_settings = False
    deleted_memories = False

    try:
        await info.cheshire_cat.destroy()
        deleted_settings = True
        deleted_memories = True
    except Exception as e:
        log.error(f"Error deleting settings: {e}")

    return ResetResponse(
        deleted_settings=deleted_settings,
        deleted_memories=deleted_memories,
        deleted_plugin_folders=False,
    )


@router.post("/agents/reset", response_model=ResetResponse)
async def agent_reset(
    info: AuthorizedInfo = check_permissions(AuthResource.CHESHIRE_CAT, AuthPermission.WRITE),
) -> ResetResponse:
    """
    Reset a single agent. This will delete all settings, memories, and metadata, for the agent.
    """
    ccat = info.cheshire_cat
    agent_id = ccat.agent_key
    try:
        await ccat.destroy()
        await info.lizard.create_cheshire_cat(agent_id)

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


@router.post("/agents/clone", response_model=AgentClonedResponse)
async def agent_clone(
    request: AgentRequest,
    info: AuthorizedInfo = check_permissions(AuthResource.CHESHIRE_CAT, AuthPermission.WRITE),
) -> AgentClonedResponse:
    """
    Clone a single agent. This will clone all settings, memories, and metadata, for the agent.
    """
    agent_id = request.agent_id
    if agent_id in crud.get_agents_main_keys():
        log.warning(f"Agent {agent_id} already exists. Cannot clone.")
        return AgentClonedResponse(cloned=False)

    ccat = info.cheshire_cat

    cloned_ccat = None
    try:
        # clone the settings from the provided agent
        log.info(f"Cloning settings from agent {ccat.agent_key} to agent {agent_id}")
        crud.clone_agent(ccat.agent_key, agent_id, ["analytics"])

        # clone the vector points from the ccat to the provided agent
        cloned_ccat = ccat.lizard.get_cheshire_cat_from_db(agent_id)
        await cloned_ccat.embed_procedures()

        log.info(f"Cloning vector memory from agent {ccat.agent_key} to agent {agent_id}")
        points, _ = await ccat.vector_memory_handler.get_all_tenant_points(
            str(VectorMemoryType.DECLARATIVE), with_vectors=True
        )
        if points:
            await cloned_ccat.vector_memory_handler.add_points_to_tenant(
                collection_name=str(VectorMemoryType.DECLARATIVE),
                payloads=[p.payload for p in points],
                vectors=[p.vector for p in points],
            )

        # clone the files from the ccat to the provided agent
        log.info(f"Cloning files from agent {ccat.agent_key} to agent {agent_id}")
        ccat.file_manager.clone_folder(ccat.agent_key, agent_id)

        return AgentClonedResponse(cloned=True)
    except Exception as e:
        log.error(f"Error cloning agent {ccat.agent_key}: {e}")

        # rollback
        if cloned_ccat:
            await cloned_ccat.destroy()
        else:
            crud.delete(agent_id)

        return AgentClonedResponse(cloned=False)
