from pydantic import BaseModel


from cheshirecat.auth.connection import AuthorizedInfo
from cheshirecat.auth.permissions import (
    AdminAuthResource,
    AuthPermission,
    AuthResource,
    check_permissions,
    check_admin_permissions,
)
from cheshirecat.looking_glass import BillTheLizard
from cheshirecat.mad_hatter.decorators import endpoint


class Item(BaseModel):
    name: str
    description: str


@endpoint.endpoint(path="/endpoint", methods=["GET"])
def test_endpoint():
    return {"result": "endpoint default prefix"}


@endpoint.endpoint(path="/endpoint", prefix="/tests", methods=["GET"], tags=["Tests"])
def test_endpoint_prefix():
    return {"result": "endpoint prefix tests"}


@endpoint.get(path="/crud", prefix="/tests", tags=["Tests"])
def test_get(info: AuthorizedInfo = check_permissions(AuthResource.PLUGINS, AuthPermission.LIST)):
    return {"result": "ok", "user_id": info.user.id}


@endpoint.get(path="/admin/crud", prefix="/tests", tags=["Tests"])
def test_get_admin(lizard: BillTheLizard = check_admin_permissions(AdminAuthResource.PLUGINS, AuthPermission.LIST)):
    return {"result": "ok"}


@endpoint.post(path="/crud", prefix="/tests", tags=["Tests"])
def test_post(item: Item):
    return {"name": item.name, "description": item.description}


@endpoint.put(path="/crud/{item_id}", prefix="/tests", tags=["Tests"])
def test_put(item_id: int, item: Item):
    return {"id": item_id, "name": item.name, "description": item.description}


@endpoint.delete(path="/crud/{item_id}", prefix="/tests", tags=["Tests"])
def test_delete(item_id: int):
    return {"id": item_id, "result": "ok"}
