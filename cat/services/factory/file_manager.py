import os
import tempfile
from abc import ABC, abstractmethod
from typing import Type, List
from pydantic import ConfigDict, BaseModel

from cat import utils
from cat.log import log
from cat.services.factory.models import BaseFactoryConfigModel


class FileResponse(BaseModel):
    path: str
    name: str
    hash: str
    size: int
    last_modified: str


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

    def read_file(self, remote_filename: str, remote_root_dir: str | None = None) -> bytes | None:
        """
        Retrieves the content of a specified file from a remote directory as bytes.

        This method constructs the complete path to the file based on the specified remote filename and the provided
        root directory, or the class's default root directory if none is given. It then retrieves the file content in
        binary format.

        Args:
            remote_filename (str): The name of the file to retrieve.
            remote_root_dir (str | None): The root directory of the remote file system where the file is stored. If None, the class's default root directory is used.

        Returns:
            bytes: The binary content of the specified file, or None if the file does not exist.
        """
        remote_root_dir = os.path.join(self._root_dir, remote_root_dir) if remote_root_dir else self._root_dir
        destination_path = os.path.join(remote_root_dir, remote_filename)

        if not self.file_exists(remote_filename, remote_root_dir):
            return None

        return self._read_file(destination_path)

    @abstractmethod
    def _download(self, file_path: str) -> bytes | None:
        pass

    @abstractmethod
    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        pass

    @abstractmethod
    def _read_file(self, file_path: str) -> bytes:
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
        if not self.file_exists(file_path):
            return False

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

    def list_files(self, remote_root_dir: str) -> List[FileResponse]:
        remote_root_dir = os.path.join(self._root_dir, remote_root_dir) if remote_root_dir else self._root_dir

        files = self._list_files(remote_root_dir)

        excluded_paths = self._excluded_dirs + self._excluded_files
        file_names = [file.name for file in files]

        return [file for file in files if not any([ex in file_names for ex in excluded_paths])]

    @abstractmethod
    def _list_files(self, remote_root_dir: str) -> List[FileResponse]:
        pass

    def clone_folder(self, remote_root_dir_from: str, remote_root_dir_to: str) -> List[str]:
        """
        Clone the entire `remote_root_dir_from` directory on the storage to the `remote_root_dir_to`.

        Args:
            remote_root_dir_from: The directory on the storage where the files are contained
            remote_root_dir_to: The directory on the storage where the files will be cloned

        Returns:
            List of the paths of the files on the storage
        """
        remote_root_dir_from = (
            os.path.join(self._root_dir, remote_root_dir_from) if remote_root_dir_from else self._root_dir
        )
        remote_root_dir_to = (
            os.path.join(self._root_dir, remote_root_dir_to) if remote_root_dir_to else self._root_dir
        )
        return self._clone_folder(remote_root_dir_from, remote_root_dir_to)

    @abstractmethod
    def _clone_folder(self, remote_root_dir_from: str, remote_root_dir_to: str) -> List[str]:
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
            for file in self.list_files(remote_root_dir)
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

        if self._root_dir not in remote_root_dir:
            remote_root_dir = os.path.join(self._root_dir, remote_root_dir)

        return filename in [file.name for file in self._list_files(remote_root_dir)]


class DummyFileManager(BaseFileManager):
    def _download(self, file_path: str) -> bytes | None:
        pass

    def _upload_file_to_storage(self, file_path: str, destination_path: str) -> str:
        return ""

    def _download_file_from_storage(self, file_path: str, local_path: str) -> str:
        return ""

    def _remove_file_from_storage(self, file_path: str) -> bool:
        return False

    def _remove_folder_from_storage(self, remote_root_dir: str) -> bool:
        return False

    def _clone_folder(self, remote_root_dir_from: str, remote_root_dir_to: str) -> List[str]:
        return []

    def _list_files(self, remote_root_dir: str) -> List[FileResponse]:
        return []

    def _read_file(self, destination_path: str) -> bytes:
        pass


class FileManagerConfig(BaseFactoryConfigModel, ABC):
    @classmethod
    def base_class(cls) -> Type[BaseFileManager]:
        return BaseFileManager

    @classmethod
    @abstractmethod
    def pyclass(cls) -> Type[BaseFileManager]:
        pass


class DummyFileManagerConfig(FileManagerConfig):
    model_config = ConfigDict(extra="forbid")

    @classmethod
    def pyclass(cls) -> Type[DummyFileManager]:
        return DummyFileManager
