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
from cat.memory.utils import ContentType, VectorMemoryCollectionTypes
from cat.utils import singleton


@singleton
class VectorMemoryBuilder:
    def __init__(self):
        # connects to Qdrant and creates self.__client attribute
        self.__client: Final = get_vector_db()

    async def build(self):
        for collection_name in VectorMemoryCollectionTypes:
            is_collection_existing = await self.__check_collection_existence(str(collection_name))
            has_same_size = (
                await self.__check_embedding_size(str(collection_name))
            ) if is_collection_existing else False
            if is_collection_existing and has_same_size:
                continue

            # Memory snapshot saving can be turned off in the .env file with:
            # SAVE_MEMORY_SNAPSHOTS=false
            if get_env("CCAT_SAVE_MEMORY_SNAPSHOTS") == "true":
                # dump collection on disk before deleting
                await self.__save_dump(str(collection_name))

            if is_collection_existing:
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

    def __get_local_alias(self, collection_name: str) -> str:
        return f"{self.lizard.embedder_name}_{collection_name}"

    async def __check_embedding_size(self, collection_name: str) -> bool:
        # Multiple vector configurations
        vectors_config = (await self.__client.get_collection(collection_name=collection_name)).config.params.vectors
        embedder_sizes = self.lizard.embedder_size

        text_lbl = str(ContentType.TEXT)
        image_lbl = str(ContentType.IMAGE)

        text_condition = text_lbl in vectors_config and vectors_config[text_lbl].size == embedder_sizes.text
        image_condition = (
            image_lbl in vectors_config and vectors_config[image_lbl].size == embedder_sizes.image
        ) if embedder_sizes.image else True

        same_size = text_condition and image_condition
        local_alias = self.__get_local_alias(collection_name)

        existing_aliases = (await self.__client.get_collection_aliases(collection_name=collection_name)).aliases

        if same_size and existing_aliases and local_alias == existing_aliases[0].alias_name:
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

        embedder_sizes = self.lizard.embedder_size

        # Create vector config for each modality
        vectors_config = {
            str(ContentType.TEXT): VectorParams(size=embedder_sizes.text, distance=Distance.COSINE)
        }

        if embedder_sizes.image:
            vectors_config[str(ContentType.IMAGE)] = VectorParams(
                size=embedder_sizes.image, distance=Distance.COSINE
            )

        try:
            await self.__client.create_collection(
                collection_name=collection_name,
                vectors_config=vectors_config,
                optimizers_config=OptimizersConfigDiff(memmap_threshold=20000, indexing_threshold=20000),
                quantization_config=ScalarQuantization(
                    scalar=ScalarQuantizationConfig(
                        type=ScalarType.INT8, quantile=0.95, always_ram=True
                    )
                ),
                # shard_number=3,
            )
        except Exception as e:
            log.error(
                f"Error creating collection {collection_name}. Try setting a higher timeout value in CCAT_QDRANT_CLIENT_TIMEOUT: {e}"
            )
            raise

        alias_name = self.__get_local_alias(collection_name)
        log.warning(f"Creating alias {alias_name} for collection \"{collection_name}\"...")
        try:
            await self.__client.update_collection_aliases(
                change_aliases_operations=[
                    CreateAliasOperation(
                        create_alias=CreateAlias(
                            collection_name=collection_name,
                            alias_name=alias_name,
                        )
                    )
                ]
            )
        except Exception as e:
            log.error(f"Error creating collection alias {alias_name} for collection {collection_name}: {e}")
            await self.__client.delete_collection(collection_name)
            log.error(f"Collection {collection_name} deleted")
            raise

        # if the client is remote, create an index on the tenant_id field
        if self.__is_db_remote():
            log.warning(f"Creating payload index for collection \"{collection_name}\"...")
            try:
                await self.__client.create_payload_index(
                    collection_name=collection_name,
                    field_name="tenant_id",
                    field_schema=PayloadSchemaType.KEYWORD
                )
            except Exception as e:
                log.error(f"Error when creating a schema index: {e}")

    def __is_db_remote(self):
        return isinstance(self.__client._client, AsyncQdrantRemote)

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