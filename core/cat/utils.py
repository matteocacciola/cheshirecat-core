import aiofiles
from datetime import timedelta
from enum import Enum as BaseEnum, EnumMeta
from fastapi import UploadFile
import inspect
from pydantic import BaseModel, ConfigDict
from langchain.evaluation import StringDistance, load_evaluator, EvaluatorType
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import PromptTemplate
from langchain_core.utils import get_colored_text
import mimetypes
import os
import shutil
import tomli
import traceback
from typing import Dict, Tuple, List, Type, TypeVar
from urllib.parse import urlparse

from cat.env import get_env
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

    def __getitem__(self, key):
        # deprecate dictionary usage
        stack = traceback.extract_stack(limit=2)
        line_code = traceback.format_list(stack)[0].split("\n")[1].strip()
        log.warning(
            f"Deprecation Warning: to get '{key}' use dot notation instead of dictionary keys, example: `obj.{key}` instead of `obj['{key}']`"
        )
        log.warning(line_code)

        # return attribute
        return getattr(self, key)

    def __setitem__(self, key, value):
        # deprecate dictionary usage
        stack = traceback.extract_stack(limit=2)
        line_code = traceback.format_list(stack)[0].split("\n")[1].strip()
        log.warning(
            f'Deprecation Warning: to set {key} use dot notation instead of dictionary keys, example: `obj.{key} = x` instead of `obj["{key}"] = x`'
        )
        log.warning(line_code)

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
    >>> print(verbal_timedelta(timedelta(days=2, weeks=1))
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


def get_base_url():
    """Allows exposing the base url."""
    secure = "s" if get_env("CCAT_CORE_USE_SECURE_PROTOCOLS") in ("true", "1") else ""
    cat_host = get_env("CCAT_CORE_HOST")
    cat_port = get_env("CCAT_CORE_PORT")
    return f"http{secure}://{cat_host}:{cat_port}/"


def get_base_path():
    """Allows exposing the base path."""
    return "cat/"


def get_plugins_path():
    """Allows exposing the plugins' path."""
    return os.path.join(get_base_path(), "plugins/")


def get_file_manager_root_storage_path():
    """Allows exposing the local storage path."""
    return os.path.join(get_base_path(), "data/storage/")


def get_static_url():
    """Allows exposing the static server url."""
    return get_base_url() + "static/"


def get_static_path():
    """Allows exposing the static files' path."""
    return os.path.join(get_base_path(), "static/")


def is_https(url):
    try:
        parsed_url = urlparse(url)
        return parsed_url.scheme == "https"
    except Exception:
        return False


def extract_domain_from_url(url):
    try:
        parsed_url = urlparse(url)
        return parsed_url.netloc + parsed_url.path
    except Exception:
        return url


def explicit_error_message(e):
    # add more explicit info on "RateLimitError" by OpenAI, 'cause people can't get it
    error_description = str(e)
    if "billing details" in error_description:
        # happens both when there are no credits or the key is not active
        error_description = """Your OpenAI key is not active or you did not add a payment method.
You need a credit card - and money in it - to use OpenAI api.
HOW TO FIX: go to your OpenAI account and add a credit card"""

        log.error(error_description)  # just to make sure the message is read both front and backend

    return error_description


def levenshtein_distance(prediction: str, reference: str) -> int:
    jaro_evaluator = load_evaluator(
        EvaluatorType.STRING_DISTANCE, distance=StringDistance.LEVENSHTEIN
    )
    result = jaro_evaluator.evaluate_strings(
        prediction=prediction,
        reference=reference,
    )
    return result["score"]


def parse_json(json_string: str, pydantic_model: BaseModel = None) -> Dict:
    # instantiate parser
    parser = JsonOutputParser(pydantic_object=pydantic_model)

    # clean to help small LLMs
    replaces = {
        "\_": "_",
        "\-": "-",
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


def match_prompt_variables(prompt_variables: Dict, prompt_template: str) -> Tuple[Dict, str]:
    """Ensure prompt variables and prompt placeholders map, so there are no issues on mismatches"""

    tmp_prompt = PromptTemplate.from_template(
        template=prompt_template
    )

    # outer set difference
    prompt_mismatches = set(prompt_variables.keys()) ^ set(tmp_prompt.input_variables)

    # clean up
    for m in prompt_mismatches:
        if m in prompt_variables.keys():
            log.warning(f"Prompt variable '{m}' not found in prompt template, removed")
            del prompt_variables[m]
        if m in tmp_prompt.input_variables:
            prompt_template = prompt_template.replace("{" + m + "}", "")
            log.warning(f"Placeholder '{m}' not found in prompt variables, removed")

    return prompt_variables, prompt_template


def get_caller_info():
    # go 2 steps up the stack
    try:
        calling_frame = inspect.currentframe()
        grand_father_frame = calling_frame.f_back.f_back
        grand_father_name = grand_father_frame.f_code.co_name

        # check if the grand_father_frame is in a class method
        if 'self' in grand_father_frame.f_locals:
            return grand_father_frame.f_locals['self'].__class__.__name__ + "." + grand_father_name
        return grand_father_name
    except Exception as e:
        log.error(e)
        return None


def langchain_log_prompt(langchain_prompt, title):
    print("\n")
    print(get_colored_text(f"==================== {title} ====================", "green"))
    for m in langchain_prompt.messages:
        print(get_colored_text(type(m).__name__, "green"))
        print(m.content)
    print(get_colored_text("========================================", "green"))
    return langchain_prompt


def langchain_log_output(langchain_output, title):
    print("\n")
    print(get_colored_text(f"==================== {title} ====================", "blue"))
    if hasattr(langchain_output, 'content'):
        print(langchain_output.content)
    else:
        print(langchain_output)
    print(get_colored_text("========================================", "blue"))
    return langchain_output


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


def empty_plugin_folder():
    # empty the plugin folder
    plugin_folder = get_plugins_path()
    for _, _, folders in os.walk(plugin_folder):
        for folder in folders:
            item = os.path.join(plugin_folder, folder)
            if os.path.isfile(item) or not os.path.exists(item):
                continue
            shutil.rmtree(item)


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