import os
from typing import Final
import aiofiles
import httpx
from qdrant_client.async_qdrant_remote import AsyncQdrantRemote
from qdrant_client.http.models import (
    Distance,
    VectorParams,
    ScalarQuantization,
    ScalarQuantizationConfig,
    ScalarType,
    CreateAliasOperation,
    CreateAlias,
    OptimizersConfigDiff,
    PayloadSchemaType,
)

from cat.db.vector_database import get_vector_db
from cat.env import get_env
from cat.log import log
from cat.memory.utils import VectorMemoryCollectionTypes
from cat.utils import singleton


@singleton
class VectorMemoryBuilder:
    def __init__(self):
        # connects to Qdrant and creates self.__client attribute
        self.__client: Final = get_vector_db()

    async def build(self):
        for collection_name in VectorMemoryCollectionTypes:
            is_collection_existing = await self.__check_collection_existence(str(collection_name))
            has_same_size = False
            if is_collection_existing:
                has_same_size = await self.__check_embedding_size(str(collection_name))

            if is_collection_existing and has_same_size:
                continue

            # Memory snapshot saving can be turned off in the .env file with:
            # SAVE_MEMORY_SNAPSHOTS=false
            if get_env("CCAT_SAVE_MEMORY_SNAPSHOTS") == "true":
                # dump collection on disk before deleting
                await self.__save_dump(str(collection_name))

            await self.__client.delete_collection(collection_name=str(collection_name))
            log.warning(f"Collection \"{collection_name}\" deleted")
            await self.__create_collection(str(collection_name))

    async def __check_collection_existence(self, collection_name: str) -> bool:
        collections_response = await self.__client.get_collections()
        if any(c.name == collection_name for c in collections_response.collections):
            # collection exists. Do nothing
            log.info(f"Collection \"{collection_name}\" already present in vector store")
            return True

        return False

    async def __check_embedding_size(self, collection_name: str) -> bool:
        # having the same size does not necessarily imply being the same embedder
        # having vectors with the same size but from different embedder in the same vector space is wrong
        same_size = (
            (await self.__client.get_collection(collection_name=collection_name)).config.params.vectors.size
            == self.lizard.embedder_size.text
        )
        local_alias = self.lizard.embedder_name + "_" + collection_name
        db_alias = (await self.__client.get_collection_aliases(collection_name=collection_name)).aliases[0].alias_name

        if same_size and local_alias == db_alias:
            log.debug(f"Collection \"{collection_name}\" has the same embedder")
            return True

        log.warning(f"Collection \"{collection_name}\" has different embedder")
        return False

    # create collection
    async def __create_collection(self, collection_name: str):
        """
        Create a new collection in the vector database.

        Args:
            collection_name: Name of the collection to create
        """

        log.warning(f"Creating collection \"{collection_name}\" ...")
        await self.__client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=self.lizard.embedder_size.text, distance=Distance.COSINE
            ),
            # hybrid mode: original vector on Disk, quantized vector in RAM
            optimizers_config=OptimizersConfigDiff(memmap_threshold=20000, indexing_threshold=20000),
            quantization_config=ScalarQuantization(
                scalar=ScalarQuantizationConfig(
                    type=ScalarType.INT8, quantile=0.95, always_ram=True
                )
            ),
            # shard_number=3,
        )

        await self.__client.update_collection_aliases(
            change_aliases_operations=[
                CreateAliasOperation(
                    create_alias=CreateAlias(
                        collection_name=collection_name,
                        alias_name=f"{self.lizard.embedder_name}_{collection_name}",
                    )
                )
            ]
        )

        # if the client is remote, create an index on the tenant_id field
        if self.__is_db_remote():
            await self.__create_payload_index("tenant_id", PayloadSchemaType.KEYWORD, collection_name)

    def __is_db_remote(self):
        return isinstance(self.__client._client, AsyncQdrantRemote)

    async def __create_payload_index(self, field_name: str, field_type: PayloadSchemaType, collection_name: str):
        """
        Create a new index on a field of the payload for an existing collection.

        Args:
            field_name: Name of the field on which to create the index
            field_type: Type of the index (es. PayloadSchemaType.KEYWORD)
            collection_name: Name of the collection on which to create the index
        """

        try:
            await self.__client.create_payload_index(
                collection_name=collection_name,
                field_name=field_name,
                field_schema=field_type
            )
        except Exception as e:
            log.error(f"Error when creating a schema index: {e}")

    # dump collection on disk before deleting
    async def __save_dump(self, collection_name: str, folder="dormouse/"):
        # only do snapshotting if using remote Qdrant
        if not self.__is_db_remote():
            return

        host = self.__client._client._host
        port = self.__client._client._port

        if os.path.isdir(folder):
            log.debug("Directory dormouse exists")
        else:
            log.info("Directory dormouse does NOT exists, creating it.")
            os.mkdir(folder)

        snapshot_info = await self.__client.create_snapshot(collection_name=collection_name)
        snapshot_url_in = (
            "http://"
            + str(host)
            + ":"
            + str(port)
            + "/collections/"
            + collection_name
            + "/snapshots/"
            + snapshot_info.name
        )
        snapshot_url_out = os.path.join(folder, snapshot_info.name)
        # rename snapshots for an easier restore in the future
        alias = (await self.__client.get_collection_aliases(collection_name=collection_name)).aliases[0].alias_name

        async with httpx.AsyncClient() as client:
            response = await client.get(snapshot_url_in)
            async with aiofiles.open(snapshot_url_out, "wb") as f:
                await f.write(response.content)  # Write the content asynchronously

        new_name = os.path.join(folder, alias.replace("/", "-") + ".snapshot")
        os.rename(snapshot_url_out, new_name)

        for s in (await self.__client.list_snapshots(collection_name=collection_name)):
            await self.__client.delete_snapshot(collection_name=collection_name, snapshot_name=s.name)
        log.warning(f"Dump \"{new_name}\" completed")

    @property
    def lizard(self) -> "BillTheLizard":
        from cat.looking_glass.bill_the_lizard import BillTheLizard
        return BillTheLizard()