import json
import mimetypes
from copy import deepcopy
from typing import Dict, List
import httpx
from fastapi import Form, APIRouter, UploadFile, BackgroundTasks, Request
from pydantic import BaseModel, Field, ConfigDict

from cat.auth.connection import AuthorizedInfo
from cat.auth.permissions import AuthPermission, AuthResource, check_permissions
from cat.exceptions import CustomValidationException
from cat.log import log
from cat.routes.routes_utils import on_upload_single_file
from cat.services.memory.utils import VectorMemoryType

router = APIRouter(tags=["Rabbit Hole"], prefix="/rabbithole")


class UploadURLConfig(BaseModel):
    url: str = Field(
        description="URL of the website to which you want to save the content"
    )
    metadata: Dict = Field(
        default={},
        description="Metadata to be stored with each chunk (e.g. author, category, etc.)"
    )
    model_config = ConfigDict(extra="forbid")


class UploadSingleFileResponse(BaseModel):
    filename: str
    content_type: str
    info: str


class UploadUrlResponse(BaseModel):
    url: str
    info: str


class AllowedMimeTypesResponse(BaseModel):
    allowed: List[str]


# receive files via http endpoint
@router.post("/batch", response_model=Dict[str, UploadSingleFileResponse])
@router.post("/batch/{chat_id}", response_model=UploadSingleFileResponse)
async def upload_files(
    files: List[UploadFile],
    background_tasks: BackgroundTasks,
    metadata: str = Form(
        default="{}",
        description="Metadata to be stored where each key is the name of a file being uploaded, and the corresponding value is another dictionary containing metadata specific to that file. "
                    "Since we are passing this along side form data, metadata must be a JSON string (use `json.dumps(metadata)`)."
    ),
    info: AuthorizedInfo = check_permissions(AuthResource.UPLOAD, AuthPermission.WRITE),
) -> Dict[str, UploadSingleFileResponse]:
    """Batch upload multiple files containing text (.txt, .md, .pdf, etc.). File content will be extracted and segmented into chunks.
    Chunks will be then vectorized and stored into documents memory.

    Note
    ----------
    `metadata` must be passed as a JSON-formatted string into the form data.
    This is necessary because the HTTP protocol does not allow file uploads to be sent as JSON.
    The maximum number of files you can upload is 1000.

    Example
    ----------
    ```
    files = []
    files_to_upload = {"sample.pdf":"application/pdf", "sample.txt":"application/txt"}

    for file_name in files_to_upload:
        content_type = files_to_upload[file_name]
        file_path = f"tests/mocks/{file_name}"
        files.append(  ("files", ((file_name, open(file_path, "rb"), content_type))) )


    metadata = {
        "sample.pdf":{
            "source": "sample.pdf",
            "title": "Test title",
            "author": "Test author",
            "year": 2020
        },
        "sample.txt":{
            "source": "sample.txt",
            "title": "Test title",
            "author": "Test author",
            "year": 2021
        }
    }

    # upload file endpoint only accepts form-encoded data
    payload = {
        "metadata": json.dumps(metadata)
    }

    response = requests.post(
        "http://localhost:1865/rabbithole/batch",
        files=files,
        data=payload
    )
    ```
    """
    log.info(f"Uploading {len(files)} files down the rabbit hole")

    response = {}
    metadata_dict = json.loads(metadata)

    for file in files:
        # if file.filename in dictionary pass the stringified metadata, otherwise pass empty dictionary-like string
        metadata_dict_current = json.dumps(metadata_dict[file.filename]) if file.filename in metadata_dict else "{}"
        on_upload_single_file(info, file, background_tasks, metadata_dict_current)

        response[file.filename] = UploadSingleFileResponse(
            filename=file.filename, content_type=file.content_type, info="File is being ingested asynchronously"
        )

    return response


@router.post("/web", response_model=UploadUrlResponse)
@router.post("/web/{chat_id}", response_model=UploadUrlResponse)
async def upload_url(
    background_tasks: BackgroundTasks,
    upload_config: UploadURLConfig,
    info: AuthorizedInfo = check_permissions(AuthResource.UPLOAD, AuthPermission.WRITE),
) -> UploadUrlResponse:
    """Upload an url. Website content will be extracted and segmented into chunks.
    Chunks will be then vectorized and stored into documents memory."""
    # check that URL is valid
    try:
        # Send a HEAD request to the specified URL
        async with httpx.AsyncClient() as client:
            response = await client.head(
                upload_config.url, headers={"User-Agent": "Magic Browser"}, follow_redirects=True
            )

        if response.status_code == 200:
            # upload file to long term memory, in the background
            background_tasks.add_task(
                info.lizard.rabbit_hole.ingest_file,
                cat=info.stray_cat or info.cheshire_cat,
                file=upload_config.url,
                **upload_config.model_dump(exclude={"url"})
            )
            return UploadUrlResponse(url=upload_config.url, info="URL is being ingested asynchronously")

        raise CustomValidationException(f"Invalid URL: {upload_config.url}")
    except httpx.RequestError:
        raise CustomValidationException(f"Unable to reach the URL: {upload_config.url}")


@router.post("/memory", response_model=UploadSingleFileResponse)
async def upload_memory(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    info: AuthorizedInfo = check_permissions(AuthResource.MEMORY, AuthPermission.WRITE),
) -> UploadSingleFileResponse:
    """Upload a memory json file to the cat memory"""
    # Get file mime type
    content_type, _ = mimetypes.guess_type(file.filename)
    log.info(f"Uploading {content_type} down the rabbit hole")
    if content_type != "application/json":
        raise CustomValidationException(
            f'MIME type {content_type} not supported. Admitted types: "application/json"'
        )

    # Ingest memories in background and notify client
    background_tasks.add_task(
        info.lizard.rabbit_hole.ingest_memory, cat=info.cheshire_cat, file=deepcopy(file)
    )

    # reply to client
    return UploadSingleFileResponse(
        filename=file.filename, content_type=file.content_type, info="Memory is being ingested asynchronously",
    )


@router.get("/allowed-mimetypes", response_model=AllowedMimeTypesResponse)
async def get_allowed_mimetypes(
    info: AuthorizedInfo = check_permissions(AuthResource.UPLOAD, AuthPermission.WRITE),
) -> AllowedMimeTypesResponse:
    """Retrieve the allowed mimetypes that can be ingested by the Rabbit Hole"""
    return AllowedMimeTypesResponse(allowed=list(info.cheshire_cat.file_handlers.keys()))


@router.get("/web", response_model=List[str])
async def get_source_urls(
    info: AuthorizedInfo = check_permissions(AuthResource.UPLOAD, AuthPermission.READ),
) -> List[str]:
    """Retrieve the list of source URLs that have been uploaded to the Rabbit Hole"""
    # Get all points
    memory_points, _ = await info.cheshire_cat.vector_memory_handler.get_all_tenant_points_from_web(
        str(VectorMemoryType.DECLARATIVE)
    )

    # retrieve all the memory points where the metadata["source"] is a URL
    return [
        memory_point.payload["metadata"]["source"]
        for memory_point in memory_points
        if (
                "metadata" in memory_point.payload
                and "source" in memory_point.payload["metadata"]
                and memory_point.payload["metadata"]["source"].startswith("http")
        )
    ]


# receive files via http endpoint
@router.post("/", response_model=UploadSingleFileResponse)
@router.post("/{chat_id}", response_model=UploadSingleFileResponse)
async def upload_file(
    file: UploadFile,
    background_tasks: BackgroundTasks,
    metadata: str = Form(
        default="{}",
        description="Metadata to be stored with each chunk (e.g. author, category, etc.). Since we are passing this along side form data, must be a JSON string (use `json.dumps(metadata)`)."
    ),
    info: AuthorizedInfo = check_permissions(AuthResource.UPLOAD, AuthPermission.WRITE),
) -> UploadSingleFileResponse:
    """Upload a file containing text (.txt, .md, .pdf, etc.). File content will be extracted and segmented into chunks.
    Chunks will be then vectorized and stored into documents memory.

    Note
    ----------
    `metadata` must be passed as a JSON-formatted string into the form data.
    This is necessary because the HTTP protocol does not allow file uploads to be sent as JSON.

    Example
    ----------
    ```
    content_type = "application/pdf"
    file_name = "sample.pdf"
    file_path = f"tests/mocks/{file_name}"
    with open(file_path, "rb") as f:
        files = {"file": (file_name, f, content_type)}

        metadata = {
            "source": "sample.pdf",
            "title": "Test title",
            "author": "Test author",
            "year": 2020,
        }
        # upload file endpoint only accepts form-encoded data
        payload = {
            "metadata": json.dumps(metadata)
        }

        response = requests.post(
            "http://localhost:1865/rabbithole/",
            files=files,
            data=payload
        )
    ```
    """
    on_upload_single_file(info, file, background_tasks, metadata)

    # reply to client
    return UploadSingleFileResponse(
        filename=file.filename, content_type=file.content_type, info="File is being ingested asynchronously"
    )
