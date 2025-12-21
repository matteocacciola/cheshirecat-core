import ast
import mimetypes
import os
import shutil
import uuid
from slugify import slugify

from cat.log import log
from cat.services.python_security import PythonSecurityVisitor, MaliciousCodeError
from cat.utils import get_allowed_plugins_mime_types


class PluginExtractor:
    def __init__(self, path: str):
        allowed_mime_types = get_allowed_plugins_mime_types()

        content_type = mimetypes.guess_type(path)[0]
        if content_type == "application/x-tar":
            self._extension = "tar"
        elif content_type == "application/zip":
            self._extension = "zip"
        else:
            raise Exception(
                f"Invalid package extension. Valid extensions are: {allowed_mime_types}"
            )

        self._path = path

        # this will be plugin folder name (its id for the mad hatter)
        self._id = self.create_plugin_id()

    @property
    def path(self):
        return self._path

    @property
    def id(self):
        return self._id

    @property
    def extension(self):
        return self._extension

    def create_plugin_id(self):
        file_name = os.path.basename(self._path)
        file_name_no_extension = os.path.splitext(file_name)[0]
        return slugify(file_name_no_extension, separator="_")

    def _is_safe_plugin(self, folder_path: str) -> bool:
        """
        Check all Python files in the plugin folder for safety.

        Args:
            folder_path (str): Path to the plugin folder.

        Returns:
            bool: True if all Python files are safe, False if any file contains malicious code.
        """
        def is_safe_python_file() -> bool:
            with open(file_path, "r", encoding="utf-8") as f:
                try:
                    tree = ast.parse(f.read())
                except SyntaxError as e:
                    log.debug(f"Syntax error in {file_path}: {e}")
                    return False
            visitor = PythonSecurityVisitor(file_path)
            try:
                visitor.visit(tree)
                return not visitor.found_malicious
            except MaliciousCodeError as e:
                log.error(f"Malicious code detected: {e}")
                return False

        for root, _, files in os.walk(folder_path):
            for file in files:
                if not file.endswith(".py"):
                    continue

                file_path = os.path.join(root, file)
                if not is_safe_python_file():
                    return False
        return True

    def extract(self, to: str) -> str:
        # create tmp directory
        tmp_folder_name = f"/tmp/{uuid.uuid1()}"
        os.makedirs(tmp_folder_name)

        # extract into tmp directory
        shutil.unpack_archive(self._path, tmp_folder_name, self._extension)
        # what was extracted?
        contents = os.listdir(tmp_folder_name)

        tmp_folder_to = (
            os.path.join(tmp_folder_name, contents[0])
            if len(contents) == 1 and os.path.isdir(os.path.join(tmp_folder_name, contents[0]))
            else tmp_folder_name
        )

        try:
            # check if plugin is safe
            if not self._is_safe_plugin(tmp_folder_to):
                raise ValueError("Plugin contains unsafe Python files")

            # proceed with installation if checks pass
            # move plugin folder to cat plugins folder
            folder_to = os.path.join(to, self._id)

            # if `folder_to` exists, delete it as it will be replaced
            if os.path.exists(folder_to):
                shutil.rmtree(folder_to)
            shutil.move(tmp_folder_to, folder_to)

            return folder_to
        except Exception as e:
            log.error(f"Error during plugin extraction: {e}")
            raise e
        finally:
            # Cleanup temporary directory
            if os.path.exists(tmp_folder_name):
                shutil.rmtree(tmp_folder_name)

            # Remove zip after extraction
            if os.path.exists(self._path):
                os.remove(self._path)
