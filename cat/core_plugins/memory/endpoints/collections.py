from typing import Dict, List
from pydantic import BaseModel

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.exceptions import CustomNotFoundException
from cat.mad_hatter.decorators import endpoint


class GetCollectionsItem(BaseModel):
    name: str
    vectors_count: int


class GetCollectionsResponse(BaseModel):
    collections: List[GetCollectionsItem]


class WipeCollectionsResponse(BaseModel):
    deleted: Dict[str, bool]


# GET a collection list with some metadata
@endpoint.get(
    "/collections", response_model=GetCollectionsResponse, tags=["Vector Memory - Collections"], prefix="/memory"
)
async def get_collections(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.READ),
) -> GetCollectionsResponse:
    """Get the list of available collections"""
    vector_memory_handler = info.cheshire_cat.vector_memory_handler
    existing_collections = await vector_memory_handler.get_collection_names()

    collections_metadata = [GetCollectionsItem(
        name=collection,
        vectors_count=await vector_memory_handler.get_vectors_count(collection)
    ) for collection in existing_collections]

    return GetCollectionsResponse(collections=collections_metadata)


# DELETE all collections
@endpoint.delete(
    "/collections", response_model=WipeCollectionsResponse, tags=["Vector Memory - Collections"], prefix="/memory"
)
async def destroy_all_collection_points(
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> WipeCollectionsResponse:
    """Delete and create all collections"""
    vector_memory_handler = info.cheshire_cat.vector_memory_handler

    to_return = {
        collection: await vector_memory_handler.destroy_all_points(collection)
        for collection in await vector_memory_handler.get_collection_names()
    }

    return WipeCollectionsResponse(deleted=to_return)


# DELETE one collection
@endpoint.delete(
    "/collections/{collection_id}",
    response_model=WipeCollectionsResponse,
    tags=["Vector Memory - Collections"],
    prefix="/memory",
)
async def destroy_all_single_collection_points(
    collection_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.DELETE),
) -> WipeCollectionsResponse:
    """Delete and recreate a collection"""
    vector_memory_handler = info.cheshire_cat.vector_memory_handler
    existing_collections = await vector_memory_handler.get_collection_names()

    # check if the collection exists
    if collection_id not in existing_collections:
        raise CustomNotFoundException("Collection does not exist.")

    ret = await vector_memory_handler.destroy_all_points(collection_id)
    return WipeCollectionsResponse(deleted={collection_id: ret})


# CREATE a new collection
@endpoint.post(
    "/collections/{collection_id}",
    response_model=GetCollectionsItem,
    tags=["Vector Memory - Collections"],
    prefix="/memory",
)
async def create_single_collection(
    collection_id: str,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.WRITE),
) -> GetCollectionsItem:
    """Create a new collection"""
    vector_memory_handler = info.cheshire_cat.vector_memory_handler

    # check if collection exists
    existing_collections = await vector_memory_handler.get_collection_names()
    if collection_id in existing_collections:
        return GetCollectionsItem(
            name=collection_id,
            vectors_count=await vector_memory_handler.get_vectors_count(collection_id)
        )

    lizard = info.cheshire_cat.lizard
    await vector_memory_handler.create_collection(
        lizard.embedder_name,
        lizard.embedder_size,
        collection_id
    )

    return GetCollectionsItem(name=collection_id, vectors_count=0)
