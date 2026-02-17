from abc import ABC, abstractmethod
from fastapi import Request, WebSocket, WebSocketException
from fastapi.requests import HTTPConnection
from pydantic import BaseModel, ConfigDict, model_validator, SkipValidation
from typing_extensions import Self

from cat.auth.auth_utils import extract_agent_id_from_request, extract_chat_id_from_request
from cat.auth.permissions import AuthPermission, AuthResource, AuthUserInfo
from cat.db.database import DEFAULT_SYSTEM_KEY
from cat.exceptions import CustomNotFoundException, CustomForbiddenException, CustomUnauthorizedException
from cat.looking_glass import BillTheLizard, CheshireCat, StrayCat


class AuthorizedInfo(BaseModel):
    agent_id: str | None
    lizard: SkipValidation[BillTheLizard]
    cheshire_cat: CheshireCat | None = None
    user: AuthUserInfo
    stray_cat: StrayCat | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    @model_validator(mode="after")
    def check_cheshire_cat(self) -> Self:
        if self.agent_id == DEFAULT_SYSTEM_KEY:
            return self

        if self.agent_id is not None and self.cheshire_cat is None:
            raise ValueError("CheshireCat cannot be None for non-system agents.")

        return self


class ConnectionAuth(ABC):
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
        is_custom_endpoint = lizard.is_custom_endpoint(url_path)
        is_triggered_by_cat = ccat is not None
        has_cat_custom_endpoint = ccat.has_custom_endpoint(url_path) if ccat is not None else False

        # if the request comes from a custom endpoint, and it is not available in the picked CheshireCat, block it and
        # return a 404-HTTP error
        if is_custom_endpoint and is_triggered_by_cat and not has_cat_custom_endpoint:
            raise CustomNotFoundException("Not Found")

        # always try core auth first (less costly, in general)
        user = None
        if not self.is_chat:
            # is that an admin able to manage agents?
            user = lizard.core_auth_handler.authorize(
                connection,
                self.resource,
                self.permission,
                lizard.agent_key,
            )

        # fallback to agent-specific auth if needed and available
        if not user and ccat is not None:
            user = ccat.custom_auth_handler.authorize(
                connection,
                self.resource,
                self.permission,
                ccat.agent_key,
            )

        # if no user was obtained, raise an exception
        if not user:
            self._not_authorized(connection)

        # if user has no permissions, raise forbidden exception
        if user and user.permissions is None:
            self._not_allowed(connection)

        if ccat is not None and (chat_id := extract_chat_id_from_request(connection)):
            stray_cat = StrayCat(
                user_data=user,
                agent_id=ccat.agent_key,
                stray_id=chat_id,
                plugin_manager_generator=ccat.plugin_manager_generator,
            )

        return AuthorizedInfo(lizard=lizard, cheshire_cat=ccat, user=user, stray_cat=stray_cat, agent_id=agent_id)

    @abstractmethod
    def _not_authorized(self, connection: HTTPConnection, **kwargs):
        pass

    @abstractmethod
    def _not_allowed(self, connection: HTTPConnection, **kwargs):
        pass


class HTTPAuth(ConnectionAuth):
    def _not_allowed(self, connection: Request, **kwargs):
        raise CustomForbiddenException("Forbidden")

    def _not_authorized(self, connection: Request, **kwargs):
        raise CustomUnauthorizedException("Unauthorized")


class WebSocketAuth(ConnectionAuth):
    def _not_allowed(self, connection: WebSocket, **kwargs):
        raise WebSocketException(code=1004, reason="Invalid Credentials")

    def _not_authorized(self, connection: WebSocket, **kwargs):
        raise WebSocketException(code=1008, reason="Unauthorized")
