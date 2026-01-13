import uuid
from typing import List, Final, Callable
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate
from langchain_core.tools import StructuredTool
from websockets.exceptions import ConnectionClosedOK

from cat import utils
from cat.auth.permissions import AuthUserInfo
from cat.log import log
from cat.looking_glass.callbacks import NewTokenHandler
from cat.looking_glass.mad_hatter.procedures import CatProcedure, CatProcedureType
from cat.looking_glass.models import AgentInput, AgentOutput, ChatResponse
from cat.looking_glass.tweedledee import Tweedledee
from cat.services.factory.agentic_workflow import AgenticTask
from cat.services.memory.messages import CatMessage, UserMessage
from cat.services.memory.utils import recall_relevant_memories_to_working_memory, VectorMemoryType
from cat.services.memory.working_memory import WorkingMemory
from cat.services.mixin import BotMixin
from cat.services.notifier import NotifierService
from cat.templates import prompts


# The Stray cat goes around tools and hook, making troubles
class StrayCat(BotMixin):
    """Session object containing user data, conversation state and many utility pointers.
    The framework creates an instance for every http request and websocket connection, making it available for plugins.

    You will be interacting with an instance of this class directly from within your plugins:

     - in `@hook` and `@endpoint` decorated functions will be passed as argument `cat` or `stray`;
     - in `@form` decorated classes you can access it via `self.cat`;
     - since `@tool` decorated functions are orchestrated by the Cat's agent, you cannot access it.

    Attributes
    ----------
    id: str
        Unique identifier of the cat session.
    user: AuthUserInfo
        User data object containing user information.
    plugin_manager_generator: Callable[[], Tweedledee]
        Function that generates the plugin manager for this cat.
    notifier: NotifierService
        Notifier service to send messages/updates to the client via Websocket.
    working_memory: WorkingMemory
        State machine containing the conversation state, persisted across conversation turns, acting as a simple
        dictionary / object. It can be used in plugins to store and retrieve data to drive the conversation or do
        anything else.
    latest_n_history: int
        Number of latest interactions (user + cat messages) to include in the agent's context.

        Examples
        --------
        Store a value in the working memory during conversation
        >> cat.working_memory["location"] = "Rome"
        or
        >> cat.working_memory.location = "Rome"

        Retrieve a value in later conversation turns
        >> cat.working_memory["location"]
        "Rome"
        >> cat.working_memory.location
        "Rome"
    """
    def __init__(
        self,
        agent_id: str,
        user_data: AuthUserInfo,
        plugin_manager_generator: Callable[[], Tweedledee],
        stray_id: str | None = None,
    ):
        self.id = stray_id or str(uuid.uuid4())
        self._agent_id: Final[str] = agent_id
        self.user: Final[AuthUserInfo] = user_data
        self.plugin_manager_generator: Final[Callable[[], Tweedledee]] = plugin_manager_generator
        self.notifier: Final[NotifierService] = NotifierService(self.user, self.agent_key, self.id)

        # bootstrap stray cat
        super().__init__()

        self.working_memory = WorkingMemory(agent_id=self.agent_key, user_id=self.user.id, chat_id=self.id)
        self.latest_n_history = 1

    def __eq__(self, other: "StrayCat") -> bool:
        """Check if two cats are equal."""
        return self.user.id == other.user.id and self.agent_key == other.agent_key and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __repr__(self):
        return f"StrayCat(id={self.id}, user_id={self.user.id}, agent_id={self.agent_key})"

    async def get_procedures(self) -> List[StructuredTool]:
        memories = await recall_relevant_memories_to_working_memory(
            cat=self,
            query=self.working_memory.user_message.text,
            collection=VectorMemoryType.PROCEDURAL,
        )

        # these are procedures from embeddings, i.e., only from CatTool or CatForm instances
        procedures = [
            lp for m in memories for lp in CatProcedure.from_document_recall(document=m, stray=self).langchainfy()
        ]

        # now, let's add the StructuredTool instances from the MCP clients using lazy loading
        mcp_clients = [p for p in self.plugin_manager.procedures if p.type == CatProcedureType.MCP]
        for mcp_client in mcp_clients:
            langchain_mcp_tools = mcp_client.inject_stray_cat(self).find_relevant_tools(
                query=self.working_memory.user_message.text,
                top_k=5
            ).langchainfy()
            procedures.extend(langchain_mcp_tools)

        return procedures

    async def __call__(self, user_message: UserMessage, **kwargs) -> CatMessage:
        """
        Run the conversation turn.

        This method is called on the user's message received from the client.

        Args:
            user_message (UserMessage): Message received from the Websocket client.

        Returns:
            final_output (CatMessage): Cat Message object, the Cat's answer to be sent to the client.

        Notes
        -----
        Here happens the main pipeline of the Cat. Namely, the Cat receives the user's input and recalls the memories.
        The retrieved context is formatted properly and given in input to the Agent that uses the LLM to produce the
        answer. This is formatted in a dictionary to be sent as a JSON via Websocket to the client.
        """
        # set up working memory for this convo turn
        # keeping track of model interactions
        self.working_memory.model_interactions = set()
        # latest user message
        self.working_memory.user_message = user_message

        plugin_manager = self.plugin_manager

        # Run a totally custom reply (skips all the side effects of the framework)
        if fast_reply := plugin_manager.execute_hook("fast_reply", None, caller=self):
            return CatMessage(text=fast_reply)

        # hook to modify/enrich user input; this is the latest user message
        self.working_memory.user_message = utils.restore_original_model(
            plugin_manager.execute_hook("before_cat_reads_message", self.working_memory.user_message, caller=self),
            UserMessage
        )

        # if the agent is set to fast reply, skip everything and return the output
        agent_fast_reply = plugin_manager.execute_hook("agent_fast_reply", AgentOutput(), caller=self)
        if agent_fast_reply and agent_fast_reply.output:
            return CatMessage(text=agent_fast_reply.output)

        # usual flow: prepare agent input with context, input and history
        latest_n_history = self.latest_n_history * 2  # each interaction has user + cat message
        agent_input = plugin_manager.execute_hook(
            "before_agent_starts",
            AgentInput(
                context=[m.document for m in self.working_memory.declarative_memories],
                input=self.working_memory.user_message.text,
                history=[h.langchainfy() for h in self.working_memory.history[-latest_n_history:]]
            ),
            caller=self,
        )

        # obtain prompt parts from plugins
        prompt_prefix = plugin_manager.execute_hook("agent_prompt_prefix", prompts.MAIN_PROMPT, caller=self)
        prompt_suffix = plugin_manager.execute_hook("agent_prompt_suffix", "", caller=self)
        prompt_variables = plugin_manager.execute_hook(
            "agent_prompt_variables",
            {"context": agent_input.context, "input": agent_input.input},
            caller=self,
        )

        system_prompt = prompt_prefix + prompt_suffix
        try:
            tools = await self.get_procedures()

            agent_output = await self.agentic_workflow.run(
                task=AgenticTask(
                    prompt=ChatPromptTemplate.from_messages([
                        SystemMessagePromptTemplate.from_template(template=system_prompt),
                        *agent_input.history,
                    ]),
                    prompt_variables=prompt_variables,
                    tools=tools,
                ),
                llm=self.large_language_model,
                callbacks=plugin_manager.execute_hook(
                    "llm_callbacks", [NewTokenHandler(self.notifier)], caller=self
                ),
            )

            if agent_output.output == utils.default_llm_answer_prompt():
                agent_output.with_llm_error = True
        except Exception as e:
            log.error(f"Agent id: {self.agent_key}. Error: {e}")
            agent_output = AgentOutput(
                output=f"An error occurred: {e}. Please, contact your support service.", with_llm_error=True
            )

        # prepare a final cat message
        final_output = CatMessage(text=agent_output.output)

        # run a message through plugins
        final_output = utils.restore_original_model(
            plugin_manager.execute_hook(
                "before_cat_sends_message", final_output, agent_output, caller=self
            ),
            CatMessage,
        )

        return final_output

    async def run_http(self, user_message: UserMessage) -> ChatResponse:
        try:
            message = await self(user_message)
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Agent id: {self.agent_key}. Error {e}")
            message = CatMessage(text="", error=str(e))

        return ChatResponse(
            agent_id=self.agent_key,
            user_id=self.user.id,
            chat_id=self.id,
            message=message,
        )

    async def run_websocket(self, user_message: UserMessage) -> None:
        try:
            cat_message = await self(user_message)
            # send a message back to a client via WS
            await self.notifier.send_chat_message(cat_message)
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Agent id: {self.agent_key}. Error {e}")
            try:
                # Send error as a websocket message
                await self.notifier.send_error(e)
            except ConnectionClosedOK as ex:
                log.warning(f"Agent id: {self.agent_key}. Warning {ex}")

    @property
    def agent_key(self):
        return self._agent_id

    @property
    def plugin_manager(self) -> Tweedledee:
        return self.plugin_manager_generator()
