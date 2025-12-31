import time
import jwt

from cat.env import get_env
from cat.auth.permissions import AuthResource, AuthPermission, get_base_permissions
from cat.auth.auth_utils import is_jwt, DEFAULT_JWT_ALGORITHM
from cat.db.database import DEFAULT_SYSTEM_KEY

from tests.utils import api_key


def test_is_jwt():
    assert not is_jwt("not_a_jwt.not_a_jwt.not_a_jwt")

    actual_jwt = jwt.encode(
        {"username": "Alice"},
        get_env("CCAT_JWT_SECRET"),
        algorithm=DEFAULT_JWT_ALGORITHM,
    )
    assert is_jwt(actual_jwt)


def test_refuse_issue_jwt(client):
    creds = {"username": "admin", "password": "wrong"}
    res = client.post("/auth/token", json=creds)

    # wrong credentials
    assert res.status_code == 401
    json = res.json()
    assert json["detail"] == "Invalid Credentials"


def test_issue_jwt(client, lizard):
    creds = {
        "username": "admin",
        "password": get_env("CCAT_ADMIN_DEFAULT_PASSWORD"),
    }

    res = client.post("/auth/token", json=creds)
    assert res.status_code == 200

    res_json = res.json()

    # did we obtain a JWT?
    assert res_json["token_type"] == "bearer"
    received_token = res_json["access_token"]
    assert is_jwt(received_token)

    # is the JWT correct for core auth handler?
    auth_handler = lizard.core_auth_handler
    user_info = auth_handler.authorize_user_from_jwt(
        received_token, AuthResource.EMBEDDER, AuthPermission.WRITE, key_id=DEFAULT_SYSTEM_KEY
    )
    assert len(user_info.id) == 36 and len(user_info.id.split("-")) == 5 # uuid4
    assert user_info.name == "admin"

    # manual JWT verification
    try:
        payload = jwt.decode(
            received_token,
            get_env("CCAT_JWT_SECRET"),
            algorithms=[DEFAULT_JWT_ALGORITHM],
        )
        assert payload["sub"] == "admin"
        assert (
            payload["exp"] - time.time() < 60 * 60 * 24
        )  # expires in less than 24 hours
    except jwt.exceptions.DecodeError:
        assert False


def test_issue_jwt_for_new_admin(client, secure_client, secure_client_headers):
    # create new user
    creds = {"username": "Alice", "password": "Alice"}

    # we should not obtain a JWT for this user
    # because it does not exist
    res = client.post("/auth/token", json=creds)
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid Credentials"

    # let's create the user
    res = secure_client.post(
        "/admins/users",
        json=creds | {"permissions": get_base_permissions()},
        headers={"Authorization": f"Bearer {api_key}"}
    )
    assert res.status_code == 200

    # now we should get a JWT
    res = client.post("/auth/token", json=creds)
    assert res.status_code == 200

    # did we obtain a JWT?
    received_token = res.json()["access_token"]
    assert is_jwt(received_token)
