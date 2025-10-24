from typing import List

from cat import AdminAuthResource, AuthPermission, BillTheLizard, check_admin_permissions, endpoint


@endpoint.get("/", prefix="/admins/core_plugins", tags=["Admins - Plugins"])
async def get_core_plugins(
    lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGIN, AuthPermission.WRITE),
) -> List[str]:
    """Get list of available core plugins"""
    return lizard.plugin_manager.get_core_plugins_ids
