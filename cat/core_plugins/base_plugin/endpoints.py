from typing import List

from cat.looking_glass import BillTheLizard
from cat.mad_hatter.decorators import endpoint
from cat.auth.permissions import check_admin_permissions, AdminAuthResource, AuthPermission


@endpoint.get("/", prefix="/admins/core_plugins", tags=["Admin Plugins"])
async def get_core_plugins(
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGINS, AuthPermission.WRITE),
) -> List[str]:
    """Get list of available core plugins"""
    return lizard.plugin_manager.get_core_plugins_ids()
