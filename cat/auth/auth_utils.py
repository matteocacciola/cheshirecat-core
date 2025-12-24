from typing import Dict, List
import bcrypt
import jwt
from fastapi.requests import HTTPConnection
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel

from cat.db.database import DEFAULT_SYSTEM_KEY

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_JWT_ALGORITHM = "HS256"


class UserInfo(BaseModel):
    user_id: str
    username: str
    permissions: Dict[str, List[str]]


def is_jwt(token: str) -> bool:
    """
    Returns whether a given string is a JWT.
    """
    try:
        # Decode the JWT without verification to check its structure
        jwt.decode(token, options={"verify_signature": False})
        return True
    except InvalidTokenError:
        return False

    
def hash_password(password: str) -> str:
    try:
        # Generate a salt
        salt = bcrypt.gensalt()
        # Hash the password
        hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
        return hashed.decode("utf-8")
    except:
        # if you try something strange, you'll stay out
        return bcrypt.gensalt().decode("utf-8")


def check_password(password: str, hashed: str) -> bool:
    try:
        # Check if the password matches the hashed password
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except:
        return False


def _extract_key_from_request(request: HTTPConnection, key: str, key_header: str) -> str:
    return request.headers.get(
        key_header,
        request.path_params.get(
            key,
            request.query_params.get(key)
        )
    )


def extract_agent_id_from_request(request: HTTPConnection) -> str | None:
    return _extract_key_from_request(request, "agent_id", "X-Agent-ID")


def extract_chat_id_from_request(request: HTTPConnection) -> str | None:
    return _extract_key_from_request(request, "chat_id", "X-Chat-ID")


def extract_user_info_on_api_key(agent_key: str, user_id: str | None = None) -> UserInfo | None:
    from cat.db.cruds import users as crud_users

    user = None
    if user_id:
        user = crud_users.get_user(agent_key, user_id)
    elif agent_key == DEFAULT_SYSTEM_KEY:
        # backward compatibility
        user = crud_users.get_user_by_username(agent_key, DEFAULT_ADMIN_USERNAME)

    if not user:
        return None

    return UserInfo(
        user_id=user["id"], username=user["username"], permissions=user["permissions"] # type: ignore
    )


def extract_token_from_request( request: HTTPConnection) -> str | None:
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
