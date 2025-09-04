from typing import Dict, List
from fastapi import APIRouter
from pydantic import BaseModel

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.exceptions import CustomNotFoundException
from cat.memory.utils import VectorMemoryCollectionTypes

router = APIRouter()


class GetCollectionsItem(BaseModel):
    name: str
    vectors_count: int


class GetCollectionsResponse(BaseModel):
    collections: List[GetCollectionsItem]


class WipeCollectionsResponse(BaseModel):
    deleted: Dict[str, bool]


# GET a collection list with some metadata
@router.get("/collections", response_model=GetCollectionsResponse)
async def get_collections(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> GetCollectionsResponse:
    """Get the list of available collections"""
    collections_metadata = [GetCollectionsItem(
        name=str(c),
        vectors_count=await info.cheshire_cat.vector_memory_handler.get_vectors_count(str(c))
    ) for c in VectorMemoryCollectionTypes]

    return GetCollectionsResponse(collections=collections_metadata)


# DELETE all collections
@router.delete("/collections", response_model=WipeCollectionsResponse)
async def destroy_all_collection_points(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> WipeCollectionsResponse:
    """Delete and create all collections"""
    ccat = info.cheshire_cat

    to_return = {
        str(c): (
            await ccat.vector_memory_handler.destroy_all_points(str(c))
        ) for c in VectorMemoryCollectionTypes
    }

    return WipeCollectionsResponse(deleted=to_return)


# DELETE one collection
@router.delete("/collections/{collection_id}", response_model=WipeCollectionsResponse)
async def destroy_all_single_collection_points(
    collection_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> WipeCollectionsResponse:
    """Delete and recreate a collection"""
    # check if collection exists
    if collection_id not in VectorMemoryCollectionTypes:
        raise CustomNotFoundException("Collection does not exist.")

    ccat = info.cheshire_cat
    ret = await ccat.vector_memory_handler.destroy_all_points(collection_id)

    return WipeCollectionsResponse(deleted={collection_id: ret})
