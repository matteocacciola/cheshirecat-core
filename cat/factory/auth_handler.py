from abc import ABC, abstractmethod
from typing import Type, Literal, Dict, List
import jwt
from fastapi.requests import HTTPConnection
from pydantic import ConfigDict

from cat.auth.auth_utils import is_jwt, extract_user_info_on_api_key, DEFAULT_JWT_ALGORITHM
from cat.auth.permissions import AuthResource, AdminAuthResource, AuthPermission, AuthUserInfo
from cat.db.cruds import users as crud_users
from cat.env import get_env
from cat.factory.base_factory import BaseFactory, BaseFactoryConfigModel
from cat.log import log


class BaseAuthHandler(ABC):
    """
    Base class to build custom Auth systems that will live alongside core auth.
    Methods `authorize_user_from_credential`
    MUST be implemented by subclasses.
    """
    # when there is no JWT, user id is passed via `user_id: xxx` header or via websocket path
    # with JWT, the user id is in the token ad has priority
    def authorize(
        self,
        request: HTTPConnection,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        """
        Authorize a user based on the request and the given resource and permission. This method will extract the token
        from the request and call the appropriate authorization method based on the protocol used. If the token is a JWT,
        it will call `authorize_user_from_jwt`, otherwise it will call `authorize_user_from_key`. If the user is
        authorized, it will return an AuthUserInfo object, otherwise it will return None.

        Args:
            request: the Starlette request to authorize the user on
            auth_resource: the resource to authorize the user on
            auth_permission: the permission to authorize the user on
            **kwargs: additional keyword arguments

        Returns:
            An AuthUserInfo object if the user is authorized, None otherwise.
        """
        # get protocol from Starlette request
        protocol = request.scope.get("type")

        # extract token from request
        token = self.extract_token(request)
        if protocol == "http":
            user_id = self.extract_user_id_http(request)
        elif protocol == "websocket":
            user_id = self.extract_user_id_websocket(request)
        else:
            log.error(f"Unknown protocol: {protocol}")
            return None

        if not token:
            return None

        if is_jwt(token):
            # JSON Web Token auth
            return self.authorize_user_from_jwt(token, auth_resource, auth_permission, **kwargs)

        # API_KEY auth
        return self.authorize_user_from_key(protocol, token, auth_resource, auth_permission, user_id, **kwargs)

    def extract_token(self, request: HTTPConnection) -> str | None:
        """
        Extract the token from a request. This method is used to extract the token from the request by inspecting either
        the `Authorization: Bearer <token>` or the `Cookie: jwt=<token>` header. It should return the token if it is
        found, otherwise it should return None.

        Args:
            request: the Starlette request to extract the token from (HTTP or Websocket)

        Returns:
            The token if it is found, None otherwise.
        """
        token = request.headers.get("Authorization", request.headers.get("Cookie"))
        if not token:
            return None
        if token.startswith("Bearer "):
            return token[len("Bearer "):]
        if token.startswith("jwt="):
            return token[len("jwt="):]
        return None

    @abstractmethod
    def extract_user_id_http(self, request: HTTPConnection) -> str | None:
        """
        Extract the requesting user_id from an HTTP request. This method is used to extract the user_id from the request
        when the user is using an HTTP protocol. It should return the token if it is found, otherwise it should return
        None.

        Args:
            request: the Starlette request to extract the token from (HTTP)

        Returns:
            The user_id if it is found, None otherwise.
        """
        # will raise: NotImplementedError
        pass

    @abstractmethod
    def extract_user_id_websocket(self, request: HTTPConnection) -> str | None:
        """
        Extract the requesting user_id from a WebSocket request. This method is used to extract the user_id from the
        request when the user is using a WebSocket protocol. It should return the user_id if it is found, otherwise it
        should return None.

        Args:
            request: the Starlette request to extract the token from (WebSocket)

        Returns:
            The user_id if it is found, None otherwise.
        """
        # will raise: NotImplementedError
        pass

    @abstractmethod
    def authorize_user_from_jwt(
        self,
        token: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        """
        Authorize a user from a JWT token. This method is used to authorize users when they are using a JWT token.

        Args:
            token: the JWT token to authorize the user from
            auth_resource: the resource to authorize the user on
            auth_permission: the permission to authorize the user on
            **kwargs: additional keyword arguments

        Returns:
            An AuthUserInfo object if the user is authorized, None otherwise.
        """
        # will raise: NotImplementedError
        pass

    @abstractmethod
    def authorize_user_from_key(
        self,
        protocol: Literal["http", "websocket"],
        api_key: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        request_user_id: str | None = None,
        **kwargs,
    ) -> AuthUserInfo | None:
        """
        Authorize a user from an API key. This method is used to authorize users when they are not using a JWT token.
        Args:
            protocol: the protocol used to authorize the user (either "http" or "websocket")
            api_key: the API key to authorize the user
            auth_resource: the resource to authorize the user on
            auth_permission: the permission to authorize the user on
            request_user_id: the user ID to authorize (it can be null)
            kwargs: additional keyword arguments

        Returns:
            An AuthUserInfo object if the user is authorized, None otherwise.
        """
        # will raise: NotImplementedError
        pass


# Core auth handler, verify token on local idp
class CoreAuthHandler(BaseAuthHandler):
    def extract_user_id_http(self, request: HTTPConnection) -> str | None:
        return request.headers.get("user_id")

    def extract_user_id_websocket(self, request: HTTPConnection) -> str | None:
        return request.query_params.get("user_id")

    def authorize_user_from_jwt(
        self,
        token: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        **kwargs,
    ) -> AuthUserInfo | None:
        key_id = kwargs.get("key_id")

        try:
            # decode token
            payload = jwt.decode(token, get_env("CCAT_JWT_SECRET"), algorithms=[DEFAULT_JWT_ALGORITHM])
        except Exception as e:
            log.error(f"Could not auth user from JWT: {e}")
            # do not pass
            return None

        # get user from DB
        user = crud_users.get_user(key_id, payload["sub"])
        if not user:
            # do not pass
            return None

        ar = str(auth_resource)
        ap = str(auth_permission)

        if ar not in user["permissions"].keys() or ap not in user["permissions"][ar]:
            # do not pass
            return None

        return AuthUserInfo(
            id=payload["sub"],
            name=payload["username"],
            permissions=user["permissions"],
            extra=user,
        )

    def authorize_user_from_key(
        self,
        protocol: Literal["http", "websocket"],
        api_key: str,
        auth_resource: AuthResource | AdminAuthResource,
        auth_permission: AuthPermission,
        request_user_id: str | None = None,
        **kwargs,
    ) -> AuthUserInfo | None:
        if not (current_api_key := get_env("CCAT_API_KEY")):
            return None
        if api_key != current_api_key:
            return None

        key_id = kwargs.get("key_id")
        if not (user_info := extract_user_info_on_api_key(key_id, request_user_id)):
            return None

        permissions: Dict[str, List[str]] | None = None
        if protocol == "websocket":
            permissions = kwargs.get("websocket_permissions", user_info.permissions)
        elif protocol == "http":
            permissions = kwargs.get("http_permissions", user_info.permissions)

        # No match -> deny access
        if not permissions:
            return None

        return AuthUserInfo(
            id=user_info.user_id,
            name=user_info.username,
            permissions=permissions
        )


class AuthHandlerConfig(BaseFactoryConfigModel, ABC):
    @classmethod
    def base_class(cls) -> Type[BaseAuthHandler]:
        return BaseAuthHandler

    @classmethod
    @abstractmethod
    def pyclass(cls) -> Type[BaseAuthHandler]:
        pass


class CoreAuthConfig(AuthHandlerConfig):
    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Standalone Core Auth Handler",
            "description": "Delegate auth to Cat core, without any additional auth systems. "
            "Do not change this if you don't know what you are doing!",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[CoreAuthHandler]:
        return CoreAuthHandler


class AuthHandlerFactory(BaseFactory):
    def get_allowed_classes(self) -> list[Type[AuthHandlerConfig]]:
        list_auth_handler_default = [
            CoreAuthConfig,
        ]

        list_auth_handler = self._hook_manager.execute_hook(
            "factory_allowed_auth_handlers", list_auth_handler_default, obj=None
        )

        return list_auth_handler

    @property
    def setting_category(self) -> str:
        return "auth_handler"

    @property
    def default_config_class(self) -> Type[BaseFactoryConfigModel]:
        return CoreAuthConfig

    @property
    def schema_name(self) -> str:
        return "authorizatorName"
