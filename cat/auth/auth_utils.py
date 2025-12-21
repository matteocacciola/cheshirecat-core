from typing import Dict, List
import bcrypt
import jwt
from fastapi.requests import HTTPConnection
from jwt.exceptions import InvalidTokenError
from pydantic import BaseModel

from cat.db.database import DEFAULT_SYSTEM_KEY

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_USER_USERNAME = "user"
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


def _extract_key_from_request(request: HTTPConnection, key: str) -> str:
    return request.headers.get(
        key,
        request.path_params.get(
            key,
            request.query_params.get(key)
        )
    )


def extract_agent_id_from_request(request: HTTPConnection) -> str | None:
    return _extract_key_from_request(request, "agent_id")


def extract_chat_id_from_request(request: HTTPConnection) -> str | None:
    return _extract_key_from_request(request, "chat_id")


def extract_user_info_on_api_key(agent_key: str, user_id: str | None = None) -> UserInfo | None:
    from cat.db.cruds import users as crud_users

    if user_id:
        user = crud_users.get_user(agent_key, user_id)
    else:
        # backward compatibility
        default = DEFAULT_ADMIN_USERNAME if agent_key == DEFAULT_SYSTEM_KEY else DEFAULT_USER_USERNAME
        user = crud_users.get_user_by_username(agent_key, default)

    if not user:
        return None

    return UserInfo(user_id=user["id"], username=user["username"], permissions=user["permissions"])
