from typing import Dict, List
from pydantic import Field
from fastapi import Depends

from cat.utils import BaseModelDict, Enum

from fastapi import Depends

class AuthResource(Enum):
    CRUD = "CRUD"
    STATUS = "STATUS"
    MEMORY = "MEMORY"
    CONVERSATION = "CONVERSATION"
    SETTINGS = "SETTINGS"
    LLM = "LLM"
    AUTH_HANDLER = "AUTH_HANDLER"
    USERS = "USERS"
    UPLOAD = "UPLOAD"
    PLUGINS = "PLUGINS"
    STATIC = "STATIC"


class AdminAuthResource(Enum):
    ADMINS = "ADMINS"
    EMBEDDER = "EMBEDDER"
    FILE_MANAGER = "FILE_MANAGER"
    CHESHIRE_CATS = "CHESHIRE_CATS"
    PLUGINS = "PLUGINS"


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
        "STATUS": ["READ"],
        "MEMORY": ["READ", "LIST"],
        "CONVERSATION": ["WRITE", "EDIT", "LIST", "READ", "DELETE"],
        "STATIC": ["READ"],
    }


def check_permissions(resource: AuthResource, permission: AuthPermission) -> "ContextualCats":
    """
    Helper function to inject cat and stray into endpoints after checking for required permissions.

    Args:
        resource (AuthResource): The resource that the user must have permission for.
        permission (AuthPermission): The permission that the user must have for the resource.

    Returns:
        ContextualCats: an instance of CheshireCat and StrayCat
    """

    from cat.auth.connection import HTTPAuth
    return Depends(HTTPAuth(resource=resource, permission=permission))


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


def check_message_permissions(resource: AuthResource, permission: AuthPermission) -> "ContextualCats":
    """
    Helper function to inject cat and stray into endpoints after checking for required permissions.

    Args:
        resource (AuthResource): The resource that the user must have permission for.
        permission (AuthPermission): The permission that the user must have for the resource.

    Returns:
        ContextualCats: an instance of CheshireCat and StrayCat
    """

    from cat.auth.connection import HTTPAuthMessage
    return Depends(HTTPAuthMessage(resource=resource, permission=permission))


def check_websocket_permissions(resource: AuthResource, permission: AuthPermission) -> "ContextualCats":
    """
    Helper function to inject cat and stray into endpoints after checking for required permissions.

    Args:
        resource (AuthResource): The resource that the user must have permission for.
        permission (AuthPermission): The permission that the user must have for the resource.

    Returns:
        ContextualCats: an instance of CheshireCat and StrayCat
    """

    from cat.auth.connection import WebSocketAuth
    return Depends(WebSocketAuth(resource=resource, permission=permission))


class AuthUserInfo(BaseModelDict):
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
    extra: BaseModelDict = Field(default_factory=dict)


def check_permissions(resource: AuthResource, permission: AuthPermission):
    """
    Helper function to inject stray into endpoints after checking for required permissions.

    Parameters
    ----------
    resource: AuthResource | str
        The resource that the user must have permission for.
    permission: AuthPermission | str
        The permission that the user must have for the resource.

    Returns
    ----------
    stray: StrayCat | None
        User session object if auth is successfull, None otherwise.
    """


    # import here to avoid circular imports
    from cat.auth.connection import HTTPAuth
    return Depends(HTTPAuth(
        # explicit convert to Enum
        resource = AuthResource(resource),
        permission = AuthPermission(permission),
    ))
