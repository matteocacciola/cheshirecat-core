import hashlib
import os
import shutil
from typing import List
from datetime import datetime

from cat.log import log
from cat.services.factory.file_manager import BaseFileManager, FileResponse


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
        def get_file_hash(file_path: str, chunk_size: int = 8192) -> str:
            sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(chunk_size):
                    sha256.update(chunk)
            return sha256.hexdigest()

        # list all the files in the directory: retrieve the full path, the size and the last modified date
        return [
            FileResponse(
                path=os.path.join(root, file),
                name=file,
                hash=get_file_hash(os.path.join(root, file)),
                size=int(os.path.getsize(os.path.join(root, file))),
                last_modified=datetime.fromtimestamp(
                    os.path.getmtime(os.path.join(root, file))
                ).strftime("%Y-%m-%d")
            )
            for root, _, files in os.walk(remote_root_dir)
            for file in files
        ]

    def _clone_folder(self, remote_root_dir_from: str, remote_root_dir_to: str) -> List[str]:
        cloned_files = []
        for root, _, files in os.walk(remote_root_dir_from):
            for file in files:
                relative_path = os.path.relpath(root, remote_root_dir_from)
                destination_dir = os.path.join(remote_root_dir_to, relative_path)
                os.makedirs(destination_dir, exist_ok=True)
                source_file = os.path.join(root, file)
                destination_file = os.path.join(destination_dir, file)
                shutil.copy2(source_file, destination_file)
                cloned_files.append(destination_file)
        return cloned_files

    def _read_file(self, destination_path: str) -> bytes:
        with open(destination_path, "rb") as f:
            return f.read()


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
            files_to_delete = [file.name for file in self.list_files(remote_root_dir)]
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

    def _clone_folder(self, remote_root_dir_from: str, remote_root_dir_to: str) -> List[str]:
        cloned_files = []
        paginator = self.s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name, Prefix=remote_root_dir_from):
            if "Contents" in page:
                for obj in page["Contents"]:
                    source_key = obj["Key"]
                    relative_path = os.path.relpath(source_key, remote_root_dir_from)
                    destination_key = os.path.join(remote_root_dir_to, relative_path)
                    copy_source = {
                        "Bucket": self.bucket_name,
                        "Key": source_key
                    }
                    self.s3.copy_object(
                        CopySource=copy_source,
                        Bucket=self.bucket_name,
                        Key=destination_key
                    )
                    cloned_files.append(destination_key)
        return cloned_files

    def _read_file(self, destination_path: str) -> bytes:
        return self.s3.get_object(Bucket=self.bucket_name, Key=destination_path)["Body"].read()


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
            for file_path in [file.name for file in self.list_files(remote_root_dir)]:
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

    def _clone_folder(self, remote_root_dir_from: str, remote_root_dir_to: str) -> List[str]:
        cloned_files = []
        for blob in self.container.list_blobs(name_starts_with=remote_root_dir_from):
            source_blob = blob.name
            relative_path = os.path.relpath(source_blob, remote_root_dir_from)
            destination_blob = os.path.join(remote_root_dir_to, relative_path)
            source_blob_client = self.container.get_blob_client(source_blob)
            destination_blob_client = self.container.get_blob_client(destination_blob)
            destination_blob_client.start_copy_from_url(source_blob_client.url)
            cloned_files.append(destination_blob)
        return cloned_files

    def _read_file(self, destination_path: str) -> bytes:
        blob_client = self.container.get_blob_client(destination_path)
        return blob_client.download_blob().readall()


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
            for file_path in [file.name for file in self.list_files(remote_root_dir)]:
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

    def _clone_folder(self, remote_root_dir_from: str, remote_root_dir_to: str) -> List[str]:
        cloned_files = []
        for blob in self.bucket.list_blobs(prefix=remote_root_dir_from):
            source_blob = blob.name
            relative_path = os.path.relpath(source_blob, remote_root_dir_from)
            destination_blob = os.path.join(remote_root_dir_to, relative_path)
            new_blob = self.bucket.blob(destination_blob)
            new_blob.rewrite(blob)
            cloned_files.append(destination_blob)
        return cloned_files

    def _read_file(self, destination_path: str) -> bytes:
        blob = self.bucket.blob(destination_path)
        return blob.download_as_bytes()


class DigitalOceanFileManager(AWSFileManager):
    pass
