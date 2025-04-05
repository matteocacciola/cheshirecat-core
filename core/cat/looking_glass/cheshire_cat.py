import time
from typing import Dict
from uuid import uuid4
from langchain_community.document_loaders.parsers.audio import FasterWhisperParser
from langchain_community.document_loaders.parsers.pdf import PDFMinerParser
from langchain_community.document_loaders.parsers.html.bs4 import BS4HTMLParser
from langchain_community.document_loaders.parsers.txt import TextParser
from langchain_community.document_loaders.parsers.language.language_parser import LanguageParser
from langchain_community.document_loaders.parsers.msword import MsWordParser
from langchain_core.embeddings import Embeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser

from cat.auth.auth_utils import hash_password, DEFAULT_USER_USERNAME
from cat.auth.permissions import get_base_permissions
from cat.db.cruds import (
    settings as crud_settings,
    history as crud_history,
    plugins as crud_plugins,
    users as crud_users,
)
from cat.factory.auth_handler import AuthHandlerFactory
from cat.factory.base_factory import ReplacedNLPConfig
from cat.factory.custom_auth_handler import BaseAuthHandler
from cat.factory.llm import LLMFactory
from cat.log import log
from cat.mad_hatter.tweedledee import Tweedledee
from cat.memory.long_term_memory import LongTermMemory
from cat.parsers import YoutubeParser, TableParser, JSONParser
from cat.services.factory_adapter import FactoryAdapter
from cat.utils import langchain_log_prompt, langchain_log_output, get_caller_info


# main class
class CheshireCat:
    """
    The Cheshire Cat.

    This is the main class that manages the whole AI application.
    It contains references to all the main modules and is responsible for the bootstrapping of the application.

    In most cases you will not need to interact with this class directly, but rather with class `StrayCat` which will be available in your plugin's hooks, tools, forms end endpoints.
    """

    def __init__(self, agent_id: str):
        """
        Cat initialization. At init time, the Cat executes the bootstrap.

        Notes
        -----
        Bootstrapping is the process of loading the plugins, the LLM, the memories.
        """

        self.id = agent_id
        self.large_language_model: BaseLanguageModel | None = None
        self.memory: LongTermMemory | None = None
        self.custom_auth_handler: BaseAuthHandler | None = None

        # instantiate plugin manager (loads all plugins' hooks and tools)
        self.plugin_manager = Tweedledee(self.id)

        # load AuthHandler
        self.load_auth()

        # allows plugins to do something before cat components are loaded
        self.plugin_manager.execute_hook("before_cat_bootstrap", cat=self)

        # load LLM
        self.load_language_model()

        # Load memories (vector collections and working_memory)
        self.load_memory()

        # After memory is loaded, we can get/create tools embeddings
        # every time the plugin_manager finishes syncing hooks, tools and forms, it will notify the Cat (so it can
        # embed tools in vector memory)
        self.plugin_manager.on_finish_plugins_sync_callback = self.embed_procedures

        # Initialize the default user if not present
        if not crud_users.get_users(self.id):
            self.initialize_users()

        # allows plugins to do something after the cat bootstrap is complete
        self.plugin_manager.execute_hook("after_cat_bootstrap", cat=self)

    def __eq__(self, other: "CheshireCat") -> bool:
        """Check if two cats are equal."""
        if not isinstance(other, CheshireCat):
            return False
        return self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"CheshireCat(agent_id={self.id})"

    def __del__(self):
        """Cat destructor."""
        self.shutdown()

    def initialize_users(self):
        user_id = str(uuid4())

        crud_users.set_users(self.id, {
            user_id: {
                "id": user_id,
                "username": DEFAULT_USER_USERNAME,
                "password": hash_password(DEFAULT_USER_USERNAME),
                # user has minor permissions
                "permissions": get_base_permissions(),
            }
        })

    def shutdown(self) -> None:
        self.memory = None
        self.custom_auth_handler = None
        self.plugin_manager = None
        self.large_language_model = None

    async def destroy(self):
        """Destroy all data from the cat."""

        await self.memory.destroy()
        self.shutdown()

        crud_settings.destroy_all(self.id)
        crud_history.destroy_all(self.id)
        crud_plugins.destroy_all(self.id)
        crud_users.destroy_all(self.id)

    def load_language_model(self):
        """Large Language Model (LLM) selection."""

        factory = LLMFactory(self.plugin_manager)

        # Custom llm
        selected_config = FactoryAdapter(factory).get_factory_config_by_settings(self.id)

        self.large_language_model = factory.get_from_config_name(self.id, selected_config["value"]["name"])

    def load_auth(self):
        factory = AuthHandlerFactory(self.plugin_manager)

        # Custom auth_handler
        selected_config = FactoryAdapter(factory).get_factory_config_by_settings(self.id)

        self.custom_auth_handler = factory.get_from_config_name(self.id, selected_config["value"]["name"])

    def load_memory(self):
        """Load LongTerMemory (which loads WorkingMemory)."""

        # instantiate long term memory
        self.memory = LongTermMemory(agent_id=self.id)

    async def embed_procedures(self):
        # Destroy all procedural embeddings
        await self.memory.vectors.procedural.destroy_all_points()

        # Easy access to active procedures in plugin_manager (source of truth!)
        active_procedures_hashes = [
            {
                "obj": ap,
                "source": ap.name,
                "type": ap.procedure_type,
                "trigger_type": trigger_type,
                "content": trigger_content,
            }
            for ap in self.plugin_manager.procedures
            for trigger_type, trigger_list in ap.triggers_map.items()
            for trigger_content in trigger_list
        ]

        payloads = []
        vectors = []
        for t in active_procedures_hashes:
            payloads.append({
                "page_content": t["content"],
                "metadata": {
                    "source": t["source"],
                    "type": t["type"],
                    "trigger_type": t["trigger_type"],
                    "when": time.time(),
                }
            })
            vectors.append(self.lizard.embedder.embed_documents([t["content"]])[0])

        await self.memory.vectors.procedural.add_points(payloads=payloads, vectors=vectors)
        log.info(f"Agent id: {self.id}. Embedded {len(active_procedures_hashes)} triggers in procedural vector memory")

    def send_ws_message(self, content: str, msg_type="notification"):
        log.error(f"Agent id: {self.id}. No websocket connection open")

    # REFACTOR: cat.llm should be available here, without streaming clearly
    # (one could be interested in calling the LLM anytime, not only when there is a session)
    def llm(self, prompt, *args, **kwargs) -> str:
        """Generate a response using the LLM model.

        This method is useful for generating a response with both a chat and a completion model using the same syntax

        Args:
            prompt (str): The prompt for generating the response.

        Returns:
            str: The generated response.
        """

        # Add a token counter to the callbacks
        caller = get_caller_info()

        # here we deal with Langchain
        prompt = ChatPromptTemplate(messages=[HumanMessage(content=prompt)])

        chain = (
            prompt
            | RunnableLambda(lambda x: langchain_log_prompt(x, f"{caller} prompt"))
            | self.large_language_model
            | RunnableLambda(lambda x: langchain_log_output(x, f"{caller} prompt output"))
            | StrOutputParser()
        )

        # in case we need to pass info to the template
        return chain.invoke({}, config=kwargs.get("config", None))

    def replace_llm(self, language_model_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current LLM with a new one. This method is used to change the LLM of the cat.
        Args:
            language_model_name: name of the new LLM
            settings: settings of the new LLM

        Returns:
            The dictionary resuming the new name and settings of the LLM
        """

        adapter = FactoryAdapter(LLMFactory(self.plugin_manager))
        updater = adapter.upsert_factory_config_by_settings(self.id, language_model_name, settings)

        try:
            # try to reload the llm of the cat
            self.load_language_model()
        except ValueError as e:
            log.error(f"Agent id: {self.id}. Error while loading the new LLM: {e}")

            # something went wrong: rollback
            adapter.rollback_factory_config(self.id)

            if updater.old_setting is not None:
                self.replace_llm(updater.old_setting["value"]["name"], updater.new_setting["value"])

            raise e

        # recreate tools embeddings
        self.plugin_manager.find_plugins()

        return ReplacedNLPConfig(name=language_model_name, value=updater.new_setting["value"])

    def replace_auth_handler(self, auth_handler_name: str, settings: Dict) -> ReplacedNLPConfig:
        """
        Replace the current Auth Handler with a new one.
        Args:
            auth_handler_name: name of the new Auth Handler
            settings: settings of the new Auth Handler

        Returns:
            The dictionary resuming the new name and settings of the Auth Handler
        """

        updater = FactoryAdapter(
            AuthHandlerFactory(self.plugin_manager)
        ).upsert_factory_config_by_settings(self.id, auth_handler_name, settings)

        self.load_auth()

        return ReplacedNLPConfig(name=auth_handler_name, value=updater.new_setting["value"])

    @property
    def lizard(self) -> "BillTheLizard":
        """
        Instance of langchain `BillTheLizard`. Use it to access the main components of the Cat.

        Returns:
            lizard: BillTheLizard
                Instance of langchain `BillTheLizard`.
        """

        from cat.looking_glass.bill_the_lizard import BillTheLizard
        return BillTheLizard()

    @property
    def websocket_manager(self) -> "BillTheLizard":
        """
        Instance of `WebsocketManager`. Use it to access the manager of the Websocket connections.

        Returns:
            websocket_manager: WebsocketManager
                Instance of `WebsocketManager`.
        """
        return self.lizard.websocket_manager

    @property
    def embedder(self) -> Embeddings:
        """
        Langchain `Embeddings` object.
        Returns:
            embedder: Langchain `Embeddings`
                Langchain embedder to turn text into a vector.

        Examples
        --------
        >>> cat.embedder.embed_query("Oh dear!")
        [0.2, 0.02, 0.4, ...]
        """

        return self.lizard.embedder

    @property
    def rabbit_hole(self) -> "RabbitHole":
        """
        Gives access to the `RabbitHole`, to upload documents and URLs into the vector DB.

        Returns:
            rabbit_hole: RabbitHole
            Module to ingest documents and URLs for RAG.
        Examples
        --------
        >>> cat.rabbit_hole.ingest_file(...)
        """

        return self.lizard.rabbit_hole

    @property
    def core_auth_handler(self) -> "CoreAuthHandler":
        """
        Gives access to the `CoreAuthHandler` object. Use it to interact with the Cat's authentication handler.

        Returns:
            core_auth_handler: CoreAuthHandler
                Core authentication handler of the Cat
        """

        return self.lizard.core_auth_handler

    @property
    def main_agent(self) -> "MainAgent":
        """
        Gives access to the `MainAgent` object. Use it to interact with the Cat's main agent.

        Returns:
            main_agent: MainAgent
                Main agent of the Cat
        """

        return self.lizard.main_agent

    @property
    def mad_hatter(self) -> Tweedledee:
        """
        Gives access to the `Tweedledee` plugin manager.

        Returns:
            mad_hatter: Tweedledee
                Module to manage plugins.

        Examples
        --------
        Obtain the path in which your plugin is located
        >>> cat.mad_hatter.get_plugin().path
        /app/cat/plugins/my_plugin
        Obtain plugin settings
        >>> cat.mad_hatter.get_plugin().load_settings()
        {"num_cats": 44, "rows": 6, "remainder": 0}
        """

        return self.plugin_manager

    @property
    def _llm(self) -> BaseLanguageModel:
        """
        Instance of langchain `LLM`.
        Only use it if you directly want to deal with langchain, prefer method `cat.llm(prompt)` otherwise.
        """

        return self.large_language_model

    # each time we access the file handlers, plugins can intervene
    @property
    def file_handlers(self) -> Dict:
        # default file handlers
        file_handlers = {
            "application/json": JSONParser(),
            "application/msword": MsWordParser(),
            "application/pdf": PDFMinerParser(),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": TableParser(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": MsWordParser(),
            "text/csv": TableParser(),
            "text/html": BS4HTMLParser(),
            "text/javascript": LanguageParser(language="js"),
            "text/markdown": TextParser(),
            "text/plain": TextParser(),
            "text/x-python": LanguageParser(language="python"),
            "video/mp4": YoutubeParser(),
            "audio/mpeg": FasterWhisperParser(),
            "audio/mp3": FasterWhisperParser(),
            "audio/ogg": FasterWhisperParser(),
            "audio/wav": FasterWhisperParser(),
            "audio/webm": FasterWhisperParser(),
        }

        # no access to stray
        file_handlers = self.plugin_manager.execute_hook(
            "rabbithole_instantiates_parsers", file_handlers, cat=self
        )

        return file_handlers

    # each time we access the text splitter, plugins can intervene
    @property
    def text_splitter(self):
        # default text splitter
        text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
            chunk_size=256,
            chunk_overlap=64,
            separators=["\\n\\n", "\n\n", ".\\n", ".\n", "\\n", "\n", " ", ""],
            encoding_name="cl100k_base",
            keep_separator=True,
            strip_whitespace=True,
            allowed_special={"\n"},  # Explicitly allow the special token ‘\n’
            disallowed_special=(),  # Disallow control for other special tokens
        )

        # no access to stray
        text_splitter = self.plugin_manager.execute_hook(
            "rabbithole_instantiates_splitter", text_splitter, cat=self
        )
        return text_splitter
