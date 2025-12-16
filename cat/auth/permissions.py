from typing import Dict, List
from fastapi import Depends
from pydantic import Field, BaseModel

from cat.utils import Enum


class AuthResource(Enum):
    MEMORY = "MEMORY"
    CHAT = "CHAT"
    SETTING = "SETTING"
    LLM = "LLM"
    AUTH_HANDLER = "AUTH_HANDLER"
    FILE_MANAGER = "FILE_MANAGER"
    CHUNKER = "CHUNKER"
    VECTOR_DATABASE = "VECTOR_DATABASE"
    USERS = "USERS"
    UPLOAD = "UPLOAD"
    PLUGIN = "PLUGIN"
    ANALYTICS = "ANALYTICS"
    ME = "ME"


class AdminAuthResource(Enum):
    ADMINS = "ADMINS"
    EMBEDDER = "EMBEDDER"
    CHESHIRE_CAT = "CHESHIRE_CAT"
    PLUGIN = "PLUGIN"
    ANALYTICS = "ANALYTICS"
    ME = "ME"


class AuthPermission(Enum):
    WRITE = "WRITE"
    EDIT = "EDIT"
    LIST = "LIST"
    READ = "READ"
    DELETE = "DELETE"


def get_full_permissions() -> Dict[str, List[str]]:
    """
    Returns all available resources and permissions.
    """
    return {str(res): [str(p) for p in AuthPermission] for res in AuthResource}


def get_full_admin_permissions() -> Dict[str, List[str]]:
    """
    Returns all available resources and permissions for an admin user.
    """
    return {str(res): [str(p) for p in AuthPermission] for res in AdminAuthResource}


def get_base_permissions() -> Dict[str, List[str]]:
    """
    Returns the default permissions for new users (chat only!).
    """
    return {
        str(AuthResource.MEMORY): [
            str(AuthPermission.LIST),
            str(AuthPermission.READ),
        ],
        str(AuthResource.CHAT): [str(p) for p in AuthPermission],
        str(AuthResource.ME): [str(p) for p in AuthPermission],
    }


def check_permissions(resource: AuthResource, permission: AuthPermission, is_chat: bool = False) -> "AuthorizedInfo":
    """
    Helper function to inject cat and stray into endpoints after checking for required permissions.

    Args:
        resource (AuthResource): The resource that the user must have permission for.
        permission (AuthPermission): The permission that the user must have for the resource.
        is_chat (bool): Whether to treat the request as a chat request.

    Returns:
        AuthorizedInfo: an instance of CheshireCat and the identified user
    """
    from cat.auth.connection import HTTPAuth
    return Depends(HTTPAuth(resource=resource, permission=permission, is_chat=is_chat))


def check_admin_permissions(resource: AdminAuthResource, permission: AuthPermission) -> "BillTheLizard":
    """
    Helper function to inject lizard into endpoints after checking for required permissions.

    Args:
        resource (AdminAuthResource): The resource that the user must have permission for.
        permission (AuthPermission): The permission that the user must have for the resource.

    Returns:
        BillTheLizard: an instance of BillTheLizard
    """
    from cat.auth.connection import AdminConnectionAuth
    return Depends(AdminConnectionAuth(resource=resource, permission=permission))


def check_websocket_permissions(resource: AuthResource, permission: AuthPermission) -> "AuthorizedInfo":
    """
    Helper function to inject cat and stray into endpoints after checking for required permissions.

    Args:
        resource (AuthResource): The resource that the user must have permission for.
        permission (AuthPermission): The permission that the user must have for the resource.

    Returns:
        AuthorizedInfo: an instance of CheshireCat and the identified user
    """
    from cat.auth.connection import WebSocketAuth
    return Depends(WebSocketAuth(resource=resource, permission=permission, is_chat=True))


class AuthUserInfo(BaseModel):
    """
    Class to represent token content after the token has been decoded.
    Will be created by AuthHandler(s) to standardize their output.
    Core will use this object to retrieve or create a StrayCat (session)
    """
    id: str
    name: str

    # permissions
    permissions: Dict[str, List[str]]

    # only put in here what you are comfortable to pass plugins:
    # - profile data
    # - custom attributes
    # - roles
    extra: Dict = Field(default_factory=dict)
