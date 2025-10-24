import asyncio
import concurrent.futures
import sys
import traceback
import socket
import base64
import hashlib
import inspect
import mimetypes
import os
from datetime import timedelta
from enum import Enum as BaseEnum, EnumMeta
from io import BytesIO
from typing import Dict, List, Type, TypeVar, Any, Callable, Union
from typing_extensions import deprecated
import aiofiles
import requests
import tomli
from PIL import Image
from fastapi import UploadFile
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, ConfigDict
from rapidfuzz.distance import Levenshtein

from cat.db import models
from cat.exceptions import CustomValidationException
from cat.log import log

_T = TypeVar("_T")


class singleton:
    instances = {}

    def __new__(cls, class_):
        def getinstance(*args, **kwargs):
            if class_ not in cls.instances:
                cls.instances[class_] = class_(*args, **kwargs)
            return cls.instances[class_]

        return getinstance


class BaseModelDict(BaseModel):
    model_config = ConfigDict(
        extra="allow",
        validate_assignment=True,
        arbitrary_types_allowed=True,
        protected_namespaces=() # avoid warning for `model_xxx` attributes
    )

    @deprecated("Use dot notation instead of dictionary keys, example: `obj.key` instead of `obj['key']`")
    def __getitem__(self, key):
        # return attribute
        return getattr(self, key)

    @deprecated("Use dot notation instead of dictionary keys, example: `obj.key = x` instead of `obj['key'] = x`")
    def __setitem__(self, key, value):
        # set attribute
        setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __delitem__(self, key):
        delattr(self, key)

    def _get_all_attributes(self):
        return self.model_dump()

    def keys(self):
        return self._get_all_attributes().keys()

    def values(self):
        return self._get_all_attributes().values()

    def items(self):
        return self._get_all_attributes().items()

    def __contains__(self, key):
        return key in self.keys()


class MetaEnum(EnumMeta):
    """
    Enables the use of the `in` operator for enums.
    For example:
    if el not in Elements:
        raise ValueError("invalid element")
    """
    def __contains__(cls, item):
        try:
            cls(item)
        except ValueError:
            return False
        return True


class Enum(BaseEnum, metaclass=MetaEnum):
    def __str__(self):
        return self.value

    def __eq__(self, other):
        if isinstance(other, Enum):
            return self.value == other.value
        return self.value == other

    def __hash__(self):
        return hash(self.value)


def to_camel_case(text: str) -> str:
    """Format string to camel case.

    Takes a string of words separated by either hyphens or underscores and returns a string of words in camel case.

    Args:
        text (str): String of hyphens or underscores separated words.

    Returns:
        Camel case formatted string.
    """
    s = text.replace("-", " ").replace("_", " ").capitalize()
    s = s.split()
    if len(text) == 0:
        return text
    return s[0] + "".join(i.capitalize() for i in s[1:])


class UpdaterFactory(BaseModel):
    old_setting: Dict | None = None
    new_setting: Dict | None = None


def verbal_timedelta(td: timedelta) -> str:
    """Convert a timedelta in human form.

    The function takes a timedelta and converts it to a human-readable string format.

    Args:
        td (timedelta): Difference between two dates.

    Returns:
        Human-readable string of time difference.

    Notes
    -----
    This method is used to give the Language Model information time information about the memories retrieved from
    the vector database.

    Examples
    --------
    >> print(verbal_timedelta(timedelta(days=2, weeks=1))
    'One week and two days ago'
    """
    if td.days != 0:
        abs_days = abs(td.days)
        abs_delta = "{} weeks".format(td.days // 7) if abs_days > 7 else "{} days".format(td.days)
    else:
        abs_minutes = abs(td.seconds) // 60
        abs_delta = "{} hours".format(abs_minutes // 60) if abs_minutes > 60 else "{} minutes".format(abs_minutes)

    if td < timedelta(0):
        return "{} ago".format(abs_delta)

    return "{} ago".format(abs_delta)


def get_base_url() -> str:
    """Allows exposing the base url."""
    return socket.gethostbyname(socket.gethostname())


def get_base_path() -> str:
    """Allows exposing the base path."""
    current_file_path = os.path.dirname(os.path.abspath(__file__))
    return current_file_path + "/"


def get_project_path():
    """Path to the folder from which the cat was run (contains data folder)"""
    return os.getcwd()


def get_core_plugins_path():
    """Core plugins' path, for internal core usage"""
    return os.path.join(get_base_path(), "core_plugins")


def get_data_path():
    """Allows exposing the data folder path."""
    return os.path.join(get_project_path(), "data")


def get_plugins_path():
    """Allows exposing the plugins' path."""
    return os.path.join(get_base_path(), "plugins")


def get_file_manager_root_storage_path() -> str:
    """Allows exposing the local storage path."""
    return os.path.join(get_data_path(), "storage")


def explicit_error_message(e) -> str:
    # add more explicit info on "RateLimitError" by OpenAI, 'cause people can't get it
    error_description = str(e)
    if "billing details" in error_description:
        # happens both when there are no credits or the key is not active
        error_description = """Your OpenAI key is not active or you did not add a payment method.
You need a credit card - and money in it - to use OpenAI api.
HOW TO FIX: go to your OpenAI account and add a credit card"""

        log.error(error_description)  # just to make sure the message is read both front and backend

    return error_description


def levenshtein_distance(prediction: str, reference: str) -> float:
    res = Levenshtein.normalized_distance(prediction, reference)
    return res


def parse_json(json_string: str, pydantic_model: BaseModel = None) -> Dict:
    # instantiate parser
    parser = JsonOutputParser(pydantic_object=pydantic_model)

    # clean to help small LLMs
    replaces = {
        "\\_": "_",
        "\\-": "-",
        "None": "null",
        "{{": "{",
        "}}": "}",
    }
    for k, v in replaces.items():
        json_string = json_string.replace(k, v)

    # first "{" occurrence (required by parser)
    start_index = json_string.index("{")

    # parse
    parsed = parser.parse(json_string[start_index:])

    if pydantic_model:
        return pydantic_model(**parsed)
    return parsed


def get_caller_info(skip: int | None = 2, return_short: bool = True, return_string: bool = True):
    """Get the name of a caller in the format module.class.method.

    Adapted from: https://gist.github.com/techtonik/2151727

    Args:
        skip (int): Specifies how many levels of stack to skip while getting caller name.
        return_short (bool): If True, returns only the caller class and method, otherwise the full path.
        return_string (bool): If True, returns the caller info as a string, otherwise as a tuple.

    Returns:
        package (str): Caller package.
        module (str): Caller module.
        klass (str): Caller class name if one otherwise None.
        caller (str): Caller function or method (if a class exist).
        line (int): The line of the call.

    Notes
    -----
    skip=1 means "who calls me",
    skip=2 "who calls my caller" etc.

    None is returned if skipped levels exceed stack height.
    """
    stack = inspect.stack()
    start = 0 + skip
    if len(stack) < start + 1:
        return None

    parentframe = stack[start][0]

    # module and packagename.
    package = ""
    module = ""
    module_info = inspect.getmodule(parentframe)
    if module_info:
        mod = module_info.__name__.split(".")
        package = mod[0]
        module = ".".join(mod[1:])

    # class name.
    klass = ""
    if "self" in parentframe.f_locals:
        klass = parentframe.f_locals["self"].__class__.__name__

    # method or function name.
    caller = None
    if parentframe.f_code.co_name != "<module>":  # top level usually
        caller = parentframe.f_code.co_name

    # call line.
    line = parentframe.f_lineno

    # Remove reference to frame
    # See: https://docs.python.org/3/library/inspect.html#the-interpreter-stack
    del parentframe

    if return_string:
        return f"{klass}.{caller}" if return_short else f"{package}.{module}.{klass}.{caller}::{line}"
    return package, module, klass, caller, line


async def load_uploaded_file(file: UploadFile, allowed_mime_types: List[str]) -> str:
    content_type, _ = mimetypes.guess_type(file.filename)
    if content_type not in allowed_mime_types:
        raise CustomValidationException(
            f'MIME type `{file.content_type}` not supported. Admitted types: {", ".join(allowed_mime_types)}'
        )

    log.info(f"Uploading {content_type} plugin {file.filename}")
    local_file_path = f"/tmp/{file.filename}"
    async with aiofiles.open(local_file_path, "wb+") as f:
        content = await file.read()
        await f.write(content)

    return local_file_path


def get_cat_version() -> str:
    with open("pyproject.toml", "rb") as f:
        project_toml = tomli.load(f)["project"]
        return project_toml["version"]


def get_allowed_plugins_mime_types() -> List:
    return ["application/zip", "application/x-tar"]


def inspect_calling_folder() -> str:
    # who's calling?
    calling_frame = inspect.currentframe().f_back.f_back
    # Get the module associated with the frame
    # Get the absolute and then relative path of the calling module's file
    abs_path = os.path.abspath(
        inspect.getabsfile(inspect.getmodule(calling_frame))
    )

    # throw exception if this method is called from outside the plugins folder
    if not abs_path.startswith(get_plugins_path()) and not abs_path.startswith(get_core_plugins_path()):
        raise Exception("get_plugin() can only be called from within a plugin")

    # Replace the root and get only the current plugin folder
    plugin_suffix = (
        abs_path.replace(get_plugins_path(), "")
        if abs_path.startswith(get_plugins_path())
        else abs_path.replace(get_core_plugins_path(), "")
    )
    if plugin_suffix.startswith("/"):
        plugin_suffix = plugin_suffix[1:]

    # Plugin's folder
    return plugin_suffix.split("/")[0]


def inspect_calling_agent() -> Union["CheshireCat", "BillTheLizard"]:
    instance = None

    # get the stack of calls
    call_stack = inspect.stack()

    # surf the stack up to the calling to load_settings()
    for frame_info in call_stack:
        frame = frame_info.frame
        if "load_settings" not in frame.f_code.co_names:
            continue

        # obtain the name of the calling Cheshire Cat class
        for k, v, in frame.f_locals.items():
            if hasattr(v, "large_language_model"):
                instance = v.cheshire_cat if hasattr(v, "cheshire_cat") else v
                break

            if hasattr(v, "_fastapi_app"):
                instance = v
                break

        if instance is not None:
            break
    if instance:
        return instance

    raise Exception("Unable to find the calling instance")


def restore_original_model(d: _T | Dict | None, model: Type[_T]) -> _T | None:
    # if _T is not a BaseModeDict, return the original object
    if not issubclass(model, BaseModel):
        return d

    # restore the original model
    if isinstance(d, Dict):
        return model(**d)

    return d


def default_llm_answer_prompt() -> str:
    return "AI: You did not configure a Language Model. Do it in the settings!"


def get_embedder_name(embedder: Embeddings) -> str:
    embedder_name = "default_embedder"
    if hasattr(embedder, "model"):
        embedder_name = embedder.model
    if hasattr(embedder, "model_name"):
        embedder_name = embedder.model_name
    if hasattr(embedder, "repo_id"):
        embedder_name = embedder.repo_id

    replaces = ["/", "-", "."]
    for v in replaces:
        embedder_name = embedder_name.replace(v, "_")

    return embedder_name.lower()


def get_factory_object(agent_id: str, factory: "BaseFactory") -> Any:
    from cat.db.cruds import settings as crud_settings

    if not (selected_config := crud_settings.get_settings_by_category(agent_id, factory.setting_category)):
        # if no config is saved, use default one and save to db
        # create the settings for the factory
        crud_settings.upsert_setting_by_name(
            agent_id,
            models.Setting(
                name=factory.default_config_class.__name__,
                category=factory.setting_category,
                value=factory.default_config,
            ),
        )
    
        # reload from db and return
        selected_config = crud_settings.get_settings_by_category(agent_id, factory.setting_category)

    return factory.get_from_config_name(agent_id, selected_config["name"])


def get_updated_factory_object(
    agent_id: str, factory: "BaseFactory", settings_name: str, settings: Dict
) -> UpdaterFactory:
    from cat.db.cruds import settings as crud_settings
    from cat.services.string_crypto import StringCrypto

    current_setting = crud_settings.get_settings_by_category(agent_id, factory.setting_category)

    # upsert the settings for the factory
    crypto = StringCrypto()
    final_setting = crud_settings.upsert_setting_by_category(agent_id, models.Setting(
        name=settings_name,
        category=factory.setting_category,
        value={
            k: crypto.encrypt(v)
            if isinstance(v, str) and any(suffix in k for suffix in ["_key", "_secret"])
            else v
            for k, v in settings.items()
        },
    ))

    return UpdaterFactory(old_setting=current_setting, new_setting=final_setting)


def get_file_hash(file_path: str, chunk_size: int = 8192) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def pod_id() -> str:
    if not os.path.exists(".pod_id"):
        p_id = hashlib.sha256(os.urandom(16)).hexdigest()[:8]
        with open(".pod_id", "w") as f:
            f.write(p_id)
        return p_id

    with open(".pod_id", "r") as f:
        p_id = f.read().strip()
    return p_id


def retrieve_image(content_image: str | None) -> str | None:
    def get_image_data() -> bytes:
        # If the image is a file, read it and encode it as a data URI
        if content_image.startswith("file://"):
            with open(content_image[7:], "rb") as f:
                image_data = f.read()
            return image_data
        # If the image is a URL, download it and encode it as a data URI.
        response = requests.get(content_image)
        response.raise_for_status()
        return response.content

    if not content_image:
        return None
    if not content_image.startswith("http") and not content_image.startswith("file://"):
        return content_image

    try:
        content = get_image_data()
        # Open the image using Pillow to determine its MIME type
        img = Image.open(BytesIO(content))
        mime_type = Image.MIME[img.format]  # e.g., "image/png"
        # Encode the image to base64
        encoded_image = base64.b64encode(content).decode("utf-8")
        # Add the image as a data URI with the correct MIME type
        return f"data:{mime_type};base64,{encoded_image}"
    except requests.RequestException as e:
        log.error(f"Failed to download image: {e} from {content_image}")
        return None


def run_sync_or_async(callback: Callable[..., Any], *args, **kwargs) -> Any:
    def run_async_in_thread():
        return asyncio.run(coro)

    if not asyncio.iscoroutinefunction(callback) and not asyncio.iscoroutine(callback):
        return callback(*args, **kwargs)

    coro = callback(*args, **kwargs)

    try:
        asyncio.get_running_loop()
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(run_async_in_thread)
            return future.result()
    except RuntimeError:
        return asyncio.run(coro)


def colored_text(text: str, color: str):
    """Get colored text.

    Args:
        text: The text to color.
        color: The color to use.

    Returns:
        The colored text. Supports blue, yellow, pink, green and red
    """
    colors = {
        "blue": "36;1",
        "yellow": "33;1",
        "pink": "38;5;200",
        "green": "32;1",
        "red": "31;1",
    }

    color_str = colors[color]
    return f"\u001b[{color_str}m\033[1;3m{text}\u001b[0m"


def print_short_traceback():
    """Print a short traceback of the last exception."""
    if sys.exc_info()[0] is not None:
        exc_type, exc_value, exc_traceback = sys.exc_info()
        formatted_traceback = traceback.format_exception(exc_type, exc_value, exc_traceback)
        if len(formatted_traceback) > 10:
            formatted_traceback = formatted_traceback[-10:]
        for err in formatted_traceback:
            print(colored_text(err, "red"))