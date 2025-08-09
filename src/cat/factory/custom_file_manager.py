import tempfile
from abc import ABC, abstractmethod
import os
from datetime import datetime
from typing import List
import shutil
from pydantic import BaseModel

from cat.log import log
from cat import utils


class FileResponse(BaseModel):
    path: str
    name: str
    hash: str
    size: int
    last_modified: str


class FileManagerAttributes(BaseModel):
    files: List[FileResponse]
    size: int


class BaseFileManager(ABC):
    """
    Base class for file storage managers. It defines the interface that all storage managers must implement. It is used
    to upload files and folders to a storage service.
    """

    def __init__(self):
        self._excluded_dirs = ["__pycache__"]
        self._excluded_files = [".gitignore", ".DS_Store", ".gitkeep", ".git", ".dockerignore"]
        self._root_dir = utils.get_file_manager_root_storage_path()

    def upload_file_to_storage(
        self, file_path: str, remote_root_dir: str, remote_filename: str | None = None
    ) -> str | None:
        """
        Upload a single file on the storage, within the directory specified by `remote_root_dir`.

        Args:
            file_path: The path of the file to upload
            remote_root_dir: The directory on the storage where the file will be uploaded
            remote_filename: The name of the file on the storage. If not specified, the file will be uploaded with its
                original name.

        Returns:
            The path of the file on the storage, None if the file has not been uploaded
        """

        remote_root_dir = os.path.join(self._root_dir, remote_root_dir) if remote_root_dir else self._root_dir
        destination_path = os.path.join(
            remote_root_dir, os.path.basename(file_path) if remote_filename is None else remote_filename
        )
        if any([ex_file in destination_path for ex_file in self._excluded_files]):
            return None

        return self._upload_file_to_storage(file_path, destination_path)

    def download(self, file_path: str) -> bytes | None:
        """
        Download a single file from the storage and return its content as bytes.

        Args:
            file_path: The path of the file to download from the storage

        Returns:
            The path of the file on the storage, None if the file has not been downloaded
        """

        file_path = os.path.join(self._root_dir, file_path)
        return self._download(file_path)

    @abstractmethod
    def _download(self, file_path: str) -> bytes | None:
        pass

    @abstractmethod
    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        pass

    def download_file_from_storage(self, file_path: str, local_dir: str) -> str | None:
        """
        Download a single file from the storage to the `local_dir`.

        Args:
            file_path: The path of the file to download
            local_dir: The directory where the file will be downloaded locally

        Returns:
            The path of the file locally if the file has been downloaded, None otherwise
        """

        local_dir = os.path.join(self._root_dir, local_dir)

        local_path = os.path.join(local_dir, os.path.basename(file_path))
        if any([ex_file in local_path for ex_file in self._excluded_files]):
            return None
        os.makedirs(local_dir, exist_ok=True)

        return self._download_file_from_storage(file_path, local_path)

    @abstractmethod
    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        pass

    def remove_file_from_storage(self, file_path: str) -> bool:
        """
        Remove a single file with `file_path` path from the storage.

        Args:
            file_path: The name/path of the file to remove, contained on the storage

        Returns:
            True if the file has been removed, False otherwise
        """

        file_path = os.path.join(self._root_dir, file_path)
        return self._remove_file_from_storage(file_path)

    @abstractmethod
    def _remove_file_from_storage(self, file_path: str) -> bool:
        pass

    def remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        """
        Remove the entire `remote_root_dir` directory from the storage. If not specified, the entire storage will be
        removed.

        Returns:
            True if the storage has been removed, False otherwise
        """

        remote_root_dir = os.path.join(self._root_dir, remote_root_dir) if remote_root_dir else self._root_dir
        return self._remove_folder_from_storage(remote_root_dir)

    @abstractmethod
    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        pass

    def get_attributes(self, remote_root_dir: str) -> FileManagerAttributes:
        """
        List of all the files contained into the `remote_root_dir` on the storage.

        Args:
            remote_root_dir: The directory on the storage where the files are contained

        Returns:
            List of the files on the storage: path, size, last modified date
        """

        remote_root_dir = os.path.join(self._root_dir, remote_root_dir) if remote_root_dir else self._root_dir
        files = self._list_files(remote_root_dir)

        excluded_paths = self._excluded_dirs + self._excluded_files
        file_names = [file.name for file in files]

        final_list = [file for file in files if not any([ex in file_names for ex in excluded_paths])]

        return FileManagerAttributes(files=final_list, size=sum(file.size for file in final_list))

    @abstractmethod
    def _list_files(self, remote_root_dir: str) -> List[FileResponse]:
        pass

    def upload_folder_to_storage(self, local_dir: str, remote_root_dir: str) -> List[str]:
        """
        Upload a directory with all the contained files on the storage, within the directory specified by
        `remote_root_dir`.

        Args:
            local_dir: The path of the directory locally, containing the files to upload to the storage
            remote_root_dir: The directory on the storage where the files will be uploaded

        Returns:
            List of the paths of the files on the storage
        """

        local_dir = os.path.join(self._root_dir, local_dir)

        return [
            self.upload_file_to_storage(os.path.join(root, file), remote_root_dir)
            for root, _, files in os.walk(local_dir)
            for file in files
        ]

    def download_folder_from_storage(self, local_dir: str, remote_root_dir: str) -> List[str]:
        """
        Download the directory specified by `remote_root_dir` with all the contained files from the storage to
        `local_dir`.

        Args:
            local_dir: The path where the directory will be downloaded locally
            remote_root_dir: The directory on the storage where the files are contained

        Returns:
            List of the paths of the files locally
        """

        return [
            self.download_file_from_storage(file.path, local_dir)
            for file in self.get_attributes(remote_root_dir).files
        ]

    def transfer(self, file_manager_from: "BaseFileManager", remote_root_dir: str) -> bool:
        """
        Transfer files from the file manager specified in the `file_manager_from` to the current one.

        Args:
            file_manager_from: The file manager to transfer the files from
            remote_root_dir: The directory on the storage where the files are contained
        """

        try:
            with tempfile.TemporaryDirectory() as tmp_folder_name:
                # try to download the files from the old file manager to the `tmp_folder_name`
                file_manager_from.download_folder_from_storage(tmp_folder_name, remote_root_dir)

                # now, try to upload the files to the new storage
                self.upload_folder_to_storage(tmp_folder_name, remote_root_dir)
                file_manager_from.remove_folder_from_storage(remote_root_dir)

                return True
        except Exception as e:
            log.error(f"Error while transferring files from the old file manager to the new one: {e}")
            return False

    def file_exists(self, filename: str, remote_root_dir: str | None = None) -> bool:
        """
        Check if a file exists in the storage.

        Args:
            filename: The name or path of the file to check
            remote_root_dir: The directory on the storage where the file should be contained

        Returns:
            True if the file exists, False otherwise
        """
        if remote_root_dir is None:
            remote_root_dir = os.path.dirname(filename)
            filename = os.path.basename(filename)

        return filename in [file.name for file in self.get_attributes(remote_root_dir).files]


class LocalFileManager(BaseFileManager):
    def _download(self, file_path: str) -> bytes | None:
        try:
            if not os.path.exists(file_path):
                return None

            with open(file_path, "rb") as f:
                return f.read()
        except Exception as e:
            log.error(f"Error while downloading file {file_path} from storage: {e}")
            return None

    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        if file_path != destination_path:
            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            # move the file from file_path to destination_path
            shutil.move(file_path, destination_path)
        return destination_path

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        if file_path != local_path:
            # move the file from origin_path to local_path
            shutil.move(file_path, local_path)
        return local_path

    def _remove_file_from_storage(self, file_path: str) -> bool:
        if os.path.exists(file_path) and os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except Exception as e:
                log.error(f"Error while removing file {file_path} from storage: {e}")
                return False
        return True

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        if os.path.exists(remote_root_dir) and os.path.isdir(remote_root_dir):
            try:
                shutil.rmtree(remote_root_dir)
            except Exception as e:
                log.error(f"Error while removing storage: {e}")
                return False
        return True

    def _list_files(self, remote_root_dir: str) -> List[FileResponse]:
        # list all the files in the directory: retrieve the full path, the size and the last modified date
        return [
            FileResponse(
                path=os.path.join(root, file),
                name=file,
                hash=utils.get_file_hash(os.path.join(root, file)),
                size=int(os.path.getsize(os.path.join(root, file))),
                last_modified=datetime.fromtimestamp(
                    os.path.getmtime(os.path.join(root, file))
                ).strftime("%Y-%m-%d")
            )
            for root, _, files in os.walk(remote_root_dir)
            for file in files
        ]


class AWSFileManager(BaseFileManager):
    def __init__(self, bucket_name: str, aws_access_key: str, aws_secret_key: str):
        import boto3
        self.s3 = boto3.client(
            "s3",
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        self.bucket_name = bucket_name
        super().__init__()

    def _download(self, file_path: str) -> bytes | None:
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=file_path)
            return response["Body"].read()
        except Exception as e:
            log.error(f"Error downloading file {file_path}: {str(e)}")
            return None

    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        self.s3.upload_file(file_path, self.bucket_name, destination_path)
        return os.path.join("s3://", self.bucket_name, destination_path)

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        self.s3.download_file(self.bucket_name, file_path, local_path)
        return local_path

    def _remove_file_from_storage(self, file_path: str) -> bool:
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=file_path)
            self.s3.delete_object(Bucket=self.bucket_name, Key=file_path)
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        try:
            files_to_delete = [file.name for file in self.get_attributes(remote_root_dir).files]
            if files_to_delete:
                objects_to_delete = [{"Key": key} for key in files_to_delete]
                self.s3.delete_objects(
                    Bucket=self.bucket_name,
                    Delete={"Objects": objects_to_delete}
                )
            return True
        except Exception as e:
            log.error(f"Error while removing storage: {e}")
            return False

    def _list_files(self, remote_root_dir: str) -> List[FileResponse]:
        files = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=remote_root_dir):
            if "Contents" in page:
                files.extend([FileResponse(
                    path=obj["Key"],
                    name=os.path.basename(obj["Key"]),
                    hash=obj.get("ETag", "").strip('"'),
                    size=int(obj["Size"]),
                    last_modified=obj["LastModified"].strftime("%Y-%m-%d"),
                ) for obj in page["Contents"] if obj["Key"] != remote_root_dir])
        return files


class AzureFileManager(BaseFileManager):
    def __init__(self, connection_string: str, container_name: str):
        from azure.storage.blob import BlobServiceClient
        self.blob_service = BlobServiceClient.from_connection_string(connection_string)
        self.container = self.blob_service.get_container_client(container_name)
        super().__init__()

    def _download(self, file_path: str) -> bytes | None:
        try:
            blob_client = self.container.get_blob_client(file_path)
            if blob_client.exists():
                return blob_client.download_blob().readall()
            return None
        except Exception as e:
            log.error(f"Error while downloading file {file_path} from storage: {e}")
            return None

    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        with open(file_path, "rb") as data:
            self.container.upload_blob(name=destination_path, data=data, overwrite=True)
        return os.path.join("azure://", self.container.container_name, destination_path)

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        blob_client = self.container.get_blob_client(file_path)
        with open(local_path, "wb") as file:
            data = blob_client.download_blob()
            file.write(data.readall())
        return local_path

    def _remove_file_from_storage(self, file_path: str) -> bool:
        try:
            blob_client = self.container.get_blob_client(file_path)
            if blob_client.exists():
                blob_client.delete_blob()
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        try:
            for file_path in [file.name for file in self.get_attributes(remote_root_dir).files]:
                blob_client = self.container.get_blob_client(file_path)
                blob_client.delete_blob()
            return True
        except Exception as e:
            log.error(f"Error while removing storage: {e}")
            return False

    def _list_files(self, remote_root_dir: str) -> List[FileResponse]:
        return [FileResponse(
            path=blob.name,
            name=os.path.basename(blob.name),
            hash=blob.etag.strip('"') if blob.etag else "",
            size=int(blob.size),
            last_modified=blob.last_modified.strftime("%Y-%m-%d"),
        ) for blob in self.container.list_blobs(name_starts_with=remote_root_dir) if blob.name != remote_root_dir]


class GoogleCloudFileManager(BaseFileManager):
    def __init__(self, bucket_name: str, credentials_path: str):
        from google.cloud import storage
        self.storage_client = storage.Client.from_service_account_json(credentials_path)
        self.bucket = self.storage_client.bucket(bucket_name)
        super().__init__()

    def _download(self, file_path: str) -> bytes | None:
        try:
            blob = self.bucket.blob(file_path)
            if blob.exists():
                return blob.download_as_bytes()
            return None
        except Exception as e:
            log.error(f"Error while downloading file {file_path} from storage: {e}")
            return None

    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        blob = self.bucket.blob(destination_path)
        blob.upload_from_filename(file_path)
        return os.path.join("gs://", self.bucket.name, destination_path)

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        blob = self.bucket.blob(file_path)
        blob.download_to_filename(local_path)
        return local_path

    def _remove_file_from_storage(self, file_path: str) -> bool:
        try:
            blob = self.bucket.blob(file_path)
            if blob.exists():
                blob.delete()
            return True
        except Exception as e:
            log.error(f"Error while removing file {file_path} from storage: {e}")
            return False

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        try:
            for file_path in [file.name for file in self.get_attributes(remote_root_dir).files]:
                blob = self.bucket.blob(file_path)
                blob.delete()
            return True
        except Exception as e:
            log.error(f"Error while removing storage: {e}")
            return False

    def _list_files(self, remote_root_dir: str) -> List[FileResponse]:
        return [FileResponse(
            path=blob.name,
            name=os.path.basename(blob.name),
            hash=blob.md5_hash.strip('"') if blob.md5_hash else "",
            size=int(blob.size),
            last_modified=blob.updated.strftime("%Y-%m-%d"),
        ) for blob in self.bucket.list_blobs(prefix=remote_root_dir) if blob.name != remote_root_dir]


class DigitalOceanFileManager(AWSFileManager):
    pass
