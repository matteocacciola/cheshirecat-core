import time
from typing import Dict
from uuid import uuid4
from langchain_community.document_loaders.parsers.pdf import PDFMinerParser
from langchain_community.document_loaders.parsers.html.bs4 import BS4HTMLParser
from langchain_community.document_loaders.parsers.txt import TextParser
from langchain_community.document_loaders.parsers.language.language_parser import LanguageParser
from langchain_community.document_loaders.parsers.msword import MsWordParser
from langchain_core.embeddings import Embeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_core.language_models import BaseLanguageModel
from langchain_core.messages import SystemMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers.string import StrOutputParser

from cat.adapters.factory_adapter import FactoryAdapter
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
from cat.mad_hatter.mad_hatter import MadHatter
from cat.mad_hatter.tweedledee import Tweedledee
from cat.memory.long_term_memory import LongTermMemory
from cat.parsers import YoutubeParser, TableParser, JSONParser
from cat.utils import langchain_log_prompt, langchain_log_output, get_caller_info


# main class
class CheshireCat:
    """
    The Cheshire Cat.

    This is the main class that manages everything for a single agent.
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

        # here we deal with motherfucking langchain
        prompt = ChatPromptTemplate(messages=[SystemMessage(content=prompt)])

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
        from cat.looking_glass.bill_the_lizard import BillTheLizard
        return BillTheLizard()

    @property
    def embedder(self) -> Embeddings:
        return self.lizard.embedder

    @property
    def rabbit_hole(self) -> "RabbitHole":
        return self.lizard.rabbit_hole

    @property
    def core_auth_handler(self) -> "CoreAuthHandler":
        return self.lizard.core_auth_handler

    @property
    def main_agent(self) -> "MainAgent":
        return self.lizard.main_agent

    @property
    def mad_hatter(self) -> MadHatter:
        return self.plugin_manager

    @property
    def _llm(self) -> MadHatter:
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
        )

        # no access to stray
        text_splitter = self.plugin_manager.execute_hook(
            "rabbithole_instantiates_splitter", text_splitter, cat=self
        )
        return text_splitter
