from abc import ABC, abstractmethod
from fastapi import Request, WebSocket, WebSocketException
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict

from cat.auth.auth_utils import extract_agent_id_from_request
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
from cat.factory.custom_auth_handler import BaseAuthHandler
from cat.looking_glass import BillTheLizard, CheshireCat


class AuthorizedInfo(BaseModel):
    cheshire_cat: CheshireCat
    user: AuthUserInfo

    model_config = ConfigDict(arbitrary_types_allowed=True)


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
    def __init__(self, resource: AuthResource, permission: AuthPermission):
        self.resource = resource
        self.permission = permission

    def __call__(self, connection: HTTPConnection) -> AuthorizedInfo:
        agent_id = extract_agent_id_from_request(connection)
        lizard: BillTheLizard = connection.app.state.lizard
        ccat = lizard.get_cheshire_cat(agent_id)

        # if the request comes from a custom endpoint, and it is not available in the picked CheshireCat, block it and
        # return a 404-HTTP error
        if (
                lizard.plugin_manager.is_custom_endpoint(connection.url.path)
                and not ccat.plugin_manager.has_custom_endpoint(connection.url.path)
        ):
            raise CustomNotFoundException("Not Found")

        user = self.get_user_from_auth_handlers(connection, lizard, ccat)
        if not user:
            # if no user was obtained, raise an exception
            self.not_allowed(connection)

        return AuthorizedInfo(cheshire_cat=ccat, user=user)

    @abstractmethod
    def get_user_from_auth_handlers(
        self, connection: HTTPConnection, lizard: BillTheLizard, ccat: CheshireCat
    ) -> AuthUserInfo | None:
        pass

    @abstractmethod
    def get_agent_user_info(
        self, connection: HTTPConnection, auth_handler: BaseAuthHandler, agent_id: str
    ) -> AuthUserInfo | None:
        pass

    @abstractmethod
    def not_allowed(self, connection: HTTPConnection, **kwargs):
        pass
        

class HTTPAuth(ConnectionAuth):
    def get_user_from_auth_handlers(
        self, connection: Request, lizard: BillTheLizard, ccat: CheshireCat
    ) -> AuthUserInfo | None:
        auth_handlers = [
            ccat.custom_auth_handler,  # try to get user from auth_handler
            lizard.core_auth_handler,  # try to get user from local id
        ]

        # is that an admin able to manage agents?
        user = lizard.core_auth_handler.authorize(
            connection,
            AdminAuthResource.CHESHIRE_CATS,
            self.permission,
            key_id=lizard.config_key,
            http_permissions=get_full_admin_permissions(),
        )

        # no admin was found? try to look for agent's users
        counter = 0
        while not user and counter < len(auth_handlers):
            user = self.get_agent_user_info(connection, auth_handlers[counter], ccat.id)
            counter += 1

        return user

    def get_agent_user_info(
        self, connection: Request, auth_handler: BaseAuthHandler, agent_id: str
    ) -> AuthUserInfo | None:
        user = auth_handler.authorize(
            connection,
            self.resource,
            self.permission,
            key_id=agent_id,
        )
        return user

    def not_allowed(self, connection: Request, **kwargs):
        raise CustomForbiddenException("Invalid Credentials")


class HTTPAuthMessage(HTTPAuth):
    def get_user_from_auth_handlers(
        self, connection: Request, lizard: BillTheLizard, ccat: CheshireCat
    ) -> AuthUserInfo | None:
        auth_handlers = [
            ccat.custom_auth_handler,  # try to get user from auth_handler
            lizard.core_auth_handler,  # try to get user from local id
        ]

        user = None
        counter = 0
        while not user and counter < len(auth_handlers):
            user = self.get_agent_user_info(connection, auth_handlers[counter], ccat.id)
            counter += 1

        return user


class WebSocketAuth(ConnectionAuth):
    def get_user_from_auth_handlers(
        self, connection: WebSocket, lizard: BillTheLizard, ccat: CheshireCat
    ) -> AuthUserInfo | None:
        auth_handlers = [
            ccat.custom_auth_handler,  # try to get user from auth_handler
            lizard.core_auth_handler,  # try to get user from local id
        ]

        user = None
        counter = 0
        while not user and counter < len(auth_handlers):
            user = self.get_agent_user_info(connection, auth_handlers[counter], ccat.id)
            counter += 1

        return user

    def get_agent_user_info(
        self, connection: WebSocket, auth_handler: BaseAuthHandler, agent_id: str
    ) -> AuthUserInfo | None:
        user_id = auth_handler.extract_user_id_websocket(connection)
        if user_id:
            crud_users.create_user(
                agent_id,
                {"id": user_id, "username": user_id, "password": user_id, "permissions": get_base_permissions()},
            )

        user = auth_handler.authorize(
            connection,
            self.resource,
            self.permission,
            key_id=agent_id,
        )
        return user

    def not_allowed(self, connection: WebSocket, **kwargs):
        raise WebSocketException(code=1004, reason="Invalid Credentials")
