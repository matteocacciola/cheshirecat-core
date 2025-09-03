import asyncio
import shutil
import aiofiles
from datetime import timedelta
from enum import Enum as BaseEnum, EnumMeta
from fastapi import UploadFile
import inspect
from pydantic import BaseModel, ConfigDict
from rapidfuzz.distance import Levenshtein
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import JsonOutputParser
import mimetypes
import os
import tomli
from typing import Dict, List, Type, TypeVar, Any, Callable
import hashlib

from cheshirecat.env import get_env
from cheshirecat.exceptions import CustomValidationException
from cheshirecat.log import log


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

    def __getitem__(self, key):
        # deprecate dictionary usage
        log.warning(
            f"Deprecation Warning: to get '{key}' use dot notation instead of dictionary keys, example: `obj.{key}` instead of `obj['{key}']`"
        )

        # return attribute
        return getattr(self, key)

    def __setitem__(self, key, value):
        # deprecate dictionary usage
        log.warning(
            f'Deprecation Warning: to set {key} use dot notation instead of dictionary keys, example: `obj.{key} = x` instead of `obj["{key}"] = x`'
        )

        # set attribute
        setattr(self, key, value)

    def get(self, key, default=None):
        return getattr(self, key, default)

    def __delitem__(self, key):
        delattr(self, key)

    def _get_all_attributes(self):
        # return {**self.model_fields, **self.__pydantic_extra__}
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
        text: str
            String of hyphens or underscores separated words.

    Returns:
        str
            Camel case formatted string.
    """
    s = text.replace("-", " ").replace("_", " ").capitalize()
    s = s.split()
    if len(text) == 0:
        return text
    return s[0] + "".join(i.capitalize() for i in s[1:])


def verbal_timedelta(td: timedelta) -> str:
    """Convert a timedelta in human form.

    The function takes a timedelta and converts it to a human-readable string format.

    Args:
        td: timedelta
            Difference between two dates.

    Returns:
        str
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
    secure = "s" if get_env("CCAT_CORE_USE_SECURE_PROTOCOLS") in ("true", "1") else ""
    cat_host = get_env("CCAT_CORE_HOST")
    cat_port = get_env("CCAT_CORE_PORT")
    return f"http{secure}://{cat_host}:{cat_port}/"


def get_base_path() -> str:
    """Allows exposing the base path."""
    current_file_path = os.path.dirname(os.path.abspath(__file__))
    return current_file_path + "/"


def get_project_path():
    """Path to the folder from which the cat was run (contains data, plugins and static folders)"""
    return os.getcwd()


def get_core_plugins_path():
    """Core plugins' path, for internal core usage"""
    return os.path.join(get_base_path(), "core_plugins")


def get_data_path():
    """Allows exposing the data folder path."""
    return os.path.join(get_project_path(), "data")


def get_plugins_path():
    """Allows exposing the plugins' path."""
    return os.path.join(get_project_path(), "plugins")


def get_static_path():
    """Allows exposing the static files' path."""
    return os.path.join(get_project_path(), "static")


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

    Parameters
    ----------
    skip: int
        Specifies how many levels of stack to skip while getting caller name.
    return_short: bool
        If True, returns only the caller class and method, otherwise the full path.
    return_string: bool
        If True, returns the caller info as a string, otherwise as a tuple.

    Returns
    -------
    package: str
        Caller package.
    module: str
        Caller module.
    klass: str
        Caller class name if one otherwise None.
    caller: str
        Caller function or method (if a class exist).
    line: int
        The line of the call.

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
    module = inspect.getmodule(calling_frame)
    # Get the absolute and then relative path of the calling module's file
    abs_path = inspect.getabsfile(module)
    rel_path = os.path.relpath(abs_path)

    # throw exception if this method is called from outside the plugins folder
    if not rel_path.startswith(get_plugins_path()):
        raise Exception("get_plugin() can only be called from within a plugin")

    # Replace the root and get only the current plugin folder
    plugin_suffix = rel_path.replace(get_plugins_path(), "")
    # Plugin's folder
    return plugin_suffix.split("/")[0]


def inspect_calling_agent() -> "CheshireCat":
    cheshire_cat_instance = None

    # get the stack of calls
    call_stack = inspect.stack()

    # surf the stack up to the calling to load_settings()
    for frame_info in call_stack:
        frame = frame_info.frame
        if 'load_settings' not in frame.f_code.co_names:
            continue

        # obtain the name of the calling Cheshire Cat class
        for k, v, in frame.f_locals.items():
            if hasattr(v, 'large_language_model'):
                cheshire_cat_instance = v.cheshire_cat if hasattr(v, 'cheshire_cat') else v
                break

        if cheshire_cat_instance is not None:
            break
    if cheshire_cat_instance:
        return cheshire_cat_instance

    raise Exception("Unable to find the calling Cheshire Cat instance")


def restore_original_model(d: _T | Dict | None, model: Type[_T]) -> _T | None:
    # if _T is not a BaseModeDict, return the original object
    if not issubclass(model, BaseModelDict):
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


def dispatch_event(func: Callable[..., Any], *args, **kwargs) -> Any:
    if not asyncio.iscoroutinefunction(func) and not asyncio.iscoroutine(func):
        return func(*args, **kwargs)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    coro = func(*args, **kwargs) if asyncio.iscoroutinefunction(func) else func
    if loop.is_running():
        return loop.create_task(coro)
    return loop.run_until_complete(coro)


def get_factory_object(agent_id: str, factory: "BaseFactory") -> Any:
    from cheshirecat.services.factory_adapter import FactoryAdapter

    selected_config = FactoryAdapter(factory).get_factory_config_by_settings(agent_id)

    return factory.get_from_config_name(agent_id, selected_config["value"]["name"])


def get_updated_factory_object(
    agent_id: str, factory: "BaseFactory", settings_name: str, settings: Dict
) -> "UpdaterFactory":
    from cheshirecat.services.factory_adapter import FactoryAdapter

    adapter = FactoryAdapter(factory)
    return adapter.upsert_factory_config_by_settings(agent_id, settings_name, settings)


def rollback_factory_config(agent_id: str, factory: "BaseFactory"):
    from cheshirecat.services.factory_adapter import FactoryAdapter

    adapter = FactoryAdapter(factory)
    adapter.rollback_factory_config(agent_id)


def get_file_hash(file_path: str, chunk_size: int = 8192) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def scaffold():
    scaffold_path = os.path.join(get_base_path(), "scaffold")
    for folder in os.listdir(scaffold_path):
        origin = os.path.join(scaffold_path, folder)
        destination = os.path.join(get_project_path(), folder)
        if not os.path.exists(destination):
            shutil.copytree(origin, destination)