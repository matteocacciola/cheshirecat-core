import asyncio
import socket
import base64
import hashlib
import inspect
import os
import threading
from enum import Enum as BaseEnum, EnumMeta
from io import BytesIO
from typing import Dict, List, Type, TypeVar, Any, Callable, Union, Generic, Tuple
from urllib.parse import urlparse
import filetype
from typing_extensions import deprecated
import requests
from PIL import Image
from langchain_core.output_parsers import JsonOutputParser
from pydantic import BaseModel, ConfigDict

from cat.log import log

_T = TypeVar("_T")


class singleton(Generic[_T]):
    instances = {}

    def __init__(self, class_: type[_T]):
        self._class = class_
        self.__wrapped__ = class_  # This helps with type checking

    def __call__(self, *args, **kwargs) -> _T:
        if self._class not in self.instances:
            self.instances[self._class] = self._class(*args, **kwargs)
        return self.instances[self._class]


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
    def __str__(self) -> str:
        return self.value

    def __eq__(self, other) -> bool:
        if isinstance(other, Enum):
            return self.value == other.value
        return self.value == other

    def __hash__(self) -> int:
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
    """
    Execute a callback function whether it's synchronous or asynchronous.

    If the callback is async and there's already a running event loop,
    it will be executed in a new event loop in a separate thread to avoid
    blocking the main event loop.

    Args:
        callback: The function to execute (sync or async)
        *args: Positional arguments to pass to the callback
        **kwargs: Keyword arguments to pass to the callback

    Returns:
        The result of the callback execution

    Raises:
        Any exception raised by the callback
    """
    # Handle async functions
    if inspect.iscoroutinefunction(callback):
        try:
            # Check if there's already a running event loop
            asyncio.get_running_loop()

            # If we're here, there's a running loop, so we need to run
            # the async function in a separate thread with its own event loop
            return _run_async_in_thread(callback(*args, **kwargs))
        except RuntimeError:
            # No running event loop, safe to use asyncio.run
            return asyncio.run(callback(*args, **kwargs))

    # Handle coroutine objects (already created coroutines)
    if inspect.iscoroutine(callback):
        try:
            asyncio.get_running_loop()
            return _run_async_in_thread(callback)
        except RuntimeError:
            return asyncio.run(callback)

    # Handle synchronous functions
    return callback(*args, **kwargs)


def _run_async_in_thread(coro) -> Any:
    """
    Run a coroutine in a new event loop in a separate thread.

    Args:
        coro: The coroutine to execute

    Returns:
        The result of the coroutine execution

    Raises:
        Any exception raised by the coroutine
    """
    result = None
    exception = None

    def thread_target():
        nonlocal result, exception
        try:
            # Create a new event loop for this thread
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)

            # Run the coroutine to completion
            result = new_loop.run_until_complete(coro)

            # Clean up
            new_loop.close()
        except Exception as e:
            exception = e

    # Start the thread and wait for it to complete
    thread = threading.Thread(target=thread_target)
    thread.start()
    thread.join()

    # Re-raise any exception that occurred in the thread
    if exception is not None:
        raise exception

    return result


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


def sanitize_permissions(permissions: Dict[str, List[str]], agent_key: str) -> Dict[str, List[str]]:
    from cat.auth.permissions import AuthAdminResource, AuthPermission, AuthResource
    from cat.db.database import DEFAULT_SYSTEM_KEY

    sanitized_permissions = {}
    is_system = agent_key == DEFAULT_SYSTEM_KEY

    for resource, perms in permissions.items():
        # Skip chat for system users or admin resources for non-system users
        if (
                (is_system and resource == AuthResource.CHAT)
                or (not is_system and resource in AuthAdminResource)
        ):
            continue

        sanitized_permissions[resource] = [perm for perm in list(set(perms)) if perm in AuthPermission]

    return sanitized_permissions


def guess_file_type(bytes_io: BytesIO) -> Tuple[str | None, str | None]:
    """
    Guess file type using the filetype library, with fallback for text files

    Args:
        bytes_io (BytesIO): The BytesIO object containing the file data.

    Returns:
        Tuple[str | None, str | None]: A tuple containing the MIME type and file extension, or (None, None) if unknown.
    """
    current_pos = bytes_io.tell()

    bytes_io.seek(0)
    kind = filetype.guess(bytes_io)

    bytes_io.seek(current_pos)

    if kind is None:
        # Fallback: check if it's a text file
        bytes_io.seek(0)
        sample = bytes_io.read(8192)  # Read first 8KB
        bytes_io.seek(current_pos)

        try:
            # Try to decode as text
            sample.decode("utf-8")
            return "text/plain", "txt"
        except (UnicodeDecodeError, AttributeError):
            # Not valid UTF-8 text
            return None, None

    return kind.mime, kind.extension


def is_url(file: str) -> bool:
    parsed_file = urlparse(file)
    # Check if a string file is a string or url
    return all([parsed_file.scheme, parsed_file.netloc])
