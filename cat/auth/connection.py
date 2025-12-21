from abc import ABC, abstractmethod
from fastapi import Request, WebSocket, WebSocketException
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict, model_validator
from typing_extensions import Self

from cat.auth.auth_utils import extract_agent_id_from_request, extract_chat_id_from_request
from cat.auth.permissions import (
    AdminAuthResource,
    AuthPermission,
    AuthResource,
    AuthUserInfo,
    get_full_admin_permissions,
    get_base_permissions,
)
from cat.db.cruds import users as crud_users
from cat.exceptions import CustomNotFoundException, CustomForbiddenException
from cat.looking_glass import BillTheLizard, CheshireCat, StrayCat


class AuthorizedInfo(BaseModel):
    agent_id: str | None
    lizard: BillTheLizard
    cheshire_cat: CheshireCat
    user: AuthUserInfo
    stray_cat: StrayCat | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def check_cheshire_cat(self) -> Self:
        if self.agent_id is not None and self.cheshire_cat is None:
            raise ValueError("CheshireCat cannot be None for non-system agents.")
        return self


class AdminConnectionAuth:
    def __init__(self, resource: AdminAuthResource, permission: AuthPermission):
        self.resource = resource
        self.permission = permission

    def __call__(self, request: Request) -> BillTheLizard:
        lizard: BillTheLizard = request.app.state.lizard

        user: AuthUserInfo = lizard.core_auth_handler.authorize(
            request,
            self.resource,
            self.permission,
            key_id=lizard.config_key,
            http_permissions=get_full_admin_permissions(),
        )
        if not user:
            # if no user was obtained, raise exception
            self.not_allowed(request)

        return lizard

    def not_allowed(self, connection: Request, **kwargs):
        raise CustomForbiddenException("Invalid Credentials")


class ConnectionAuth(ABC):
    from cat.factory.auth_handler import BaseAuthHandler

    def __init__(self, resource: AuthResource, permission: AuthPermission, is_chat: bool = False):
        self.resource = resource
        self.permission = permission
        self.is_chat = is_chat

    def __call__(self, connection: HTTPConnection) -> AuthorizedInfo:
        lizard: BillTheLizard = connection.app.state.lizard

        agent_id = extract_agent_id_from_request(connection)
        ccat = lizard.get_cheshire_cat(agent_id) if agent_id else None

        stray_cat = None

        url_path = connection.url.path
        is_custom_endpoint = lizard.plugin_manager.is_custom_endpoint(url_path)

        # if the request comes from a custom endpoint, and it is not available in the picked CheshireCat, block it and
        # return a 404-HTTP error
        if (
                is_custom_endpoint
                and (ccat is None or not ccat.plugin_manager.has_custom_endpoint(url_path))
        ):
            raise CustomNotFoundException("Not Found")

        # always try core auth first (less costly, in general)
        user = None
        if not self.is_chat:
            # is that an admin able to manage agents?
            user = lizard.core_auth_handler.authorize(
                connection,
                AdminAuthResource.CHESHIRE_CAT,
                self.permission,
                key_id=lizard.config_key,
                http_permissions=get_full_admin_permissions(),
            )

        # fallback to agent-specific auth if needed and available
        if not user and ccat is not None:
            self._before_get_agent_user_info(connection, ccat.custom_auth_handler, agent_id)
            user = ccat.custom_auth_handler.authorize(
                connection,
                self.resource,
                self.permission,
                key_id=ccat.id,
            )

        # if no user was obtained, raise an exception
        if not user:
            self._not_allowed(connection)

        if ccat is not None and (chat_id := extract_chat_id_from_request(connection)):
            stray_cat = StrayCat(user_data=user, agent_id=ccat.id, stray_id=chat_id)

        return AuthorizedInfo(lizard=lizard, cheshire_cat=ccat, user=user, stray_cat=stray_cat, agent_id=agent_id)

    @abstractmethod
    def _before_get_agent_user_info(self, connection: HTTPConnection, auth_handler: BaseAuthHandler, agent_id: str):
        pass

    @abstractmethod
    def _not_allowed(self, connection: HTTPConnection, **kwargs):
        pass


class HTTPAuth(ConnectionAuth):
    from cat.factory.auth_handler import BaseAuthHandler

    def _before_get_agent_user_info(self, connection: Request, auth_handler: BaseAuthHandler, agent_id: str):
        pass

    def _not_allowed(self, connection: Request, **kwargs):
        raise CustomForbiddenException("Invalid Credentials")


class WebSocketAuth(ConnectionAuth):
    from cat.factory.auth_handler import BaseAuthHandler

    def _before_get_agent_user_info(self, connection: WebSocket, auth_handler: BaseAuthHandler, agent_id: str):
        user_id = auth_handler.extract_user_id_websocket(connection)
        if not user_id:
            return
        crud_users.create_user(
            agent_id,
            {"id": user_id, "username": user_id, "password": user_id, "permissions": get_base_permissions()},
        )

    def _not_allowed(self, connection: WebSocket, **kwargs):
        raise WebSocketException(code=1004, reason="Invalid Credentials")
