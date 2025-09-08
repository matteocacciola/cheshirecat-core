from fastapi import Request, FastAPI
from fastapi.staticfiles import StaticFiles

from cat.auth.connection import HTTPAuth
from cat.auth.permissions import AuthPermission, AuthResource
from cat.utils import get_static_path


class AuthStatic(StaticFiles):
    async def __call__(self, scope, receive, send) -> None:
        request = Request(scope, receive=receive)
        http_auth = HTTPAuth(resource=AuthResource.STATIC, permission=AuthPermission.READ)
        http_auth(request)
        await super().__call__(scope, receive, send)


def mount(cheshire_cat_api: FastAPI):
    # static files folder available to plugins
    cheshire_cat_api.mount(
        "/static/", AuthStatic(directory=get_static_path()), name="static"
    )
