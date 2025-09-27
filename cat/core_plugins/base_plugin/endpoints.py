from typing import List

from cat.auth.permissions import check_admin_permissions, AdminAuthResource, AuthPermission
from cat.looking_glass import BillTheLizard
from cat.mad_hatter.decorators import endpoint


@endpoint.get("/", prefix="/admins/core_plugins", tags=["Admin Plugins"])
async def get_core_plugins(
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.WRITE),
) -> List[str]:
    """Get list of available core plugins"""
    return lizard.plugin_manager.get_core_plugins_ids
