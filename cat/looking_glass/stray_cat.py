from typing import Literal, List, Dict, Any, get_args, Final
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, BasePromptTemplate, HumanMessagePromptTemplate
from langchain_core.runnables import RunnableConfig, RunnableLambda
from websockets.exceptions import ConnectionClosedOK

from cat import utils
from cat.auth.permissions import AuthUserInfo
from cat.factory.agent import LLMAction, CatAgent, AgentOutput
from cat.log import log
from cat.looking_glass.bill_the_lizard import BillTheLizard
from cat.looking_glass.callbacks import NewTokenHandler
from cat.looking_glass.white_rabbit import WhiteRabbit
from cat.mad_hatter import Tweedledee, CatProcedure
from cat.memory.messages import CatMessage, UserMessage
from cat.memory.working_memory import WorkingMemory
from cat.rabbit_hole import RabbitHole
from cat.services.websocket_manager import WebSocketManager


MSG_TYPES = Literal["notification", "chat", "error", "chat_token"]


# The Stray cat goes around tools and hook, making troubles
class StrayCat:
    """Session object containing user data, conversation state and many utility pointers.
    The framework creates an instance for every http request and websocket connection, making it available for plugins.

    You will be interacting with an instance of this class directly from within your plugins:

     - in `@hook`, `@tool` and `@endpoint` decorated functions will be passed as argument `cat` or `stray`
     - in `@form` decorated classes you can access it via `self.cat`

    Attributes
    ----------
    user : AuthUserInfo
        User data object containing user information.
    agent_id : str
        The ID of the agent associated with this cat.
    working_memory : WorkingMemory
        State machine containing the conversation state, persisted across conversation turns, acting as a simple
        dictionary / object. It can be used in plugins to store and retrieve data to drive the conversation or do
        anything else.

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
    def __init__(self, agent_id: str, user_data: AuthUserInfo):
        self.agent_id: Final[str] = agent_id
        self.user: Final[AuthUserInfo] = user_data

        self.working_memory = WorkingMemory(agent_id=self.agent_id, user_id=self.user.id)

    def __eq__(self, other: "StrayCat") -> bool:
        """Check if two cats are equal."""
        return self.user.id == other.user.id

    def __hash__(self):
        return hash(self.user.id)

    def __repr__(self):
        return f"StrayCat(user_id={self.user.id}, agent_id={self.agent_id})"

    async def _send_ws_json(self, data: Any):
        ws_connection = self.websocket_manager.get_connection(self.user.id)
        if not ws_connection:
            log.debug(f"No websocket connection is open for user {self.user.id}")
            return

        try:
            await ws_connection.send_json(data)
        except RuntimeError as e:
            log.error(f"Runtime error occurred while sending data: {e}")

    async def send_ws_message(self, content: str, msg_type: MSG_TYPES = "notification"):
        """
        Send a message via websocket.

        This method is useful for sending a message via websocket directly without passing through the LLM.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
        content: str
            The content of the message.
        msg_type: str
            The type of the message. Should be either `notification` (default), `chat`, `chat_token` or `error`

        Examples
        --------
        Send a notification via websocket
        >> cat.send_ws_message("Hello, I'm a notification!")
        Send a chat message via websocket
        >> cat.send_ws_message("Meooow!", msg_type="chat")

        Send an error message via websocket
        >> cat.send_ws_message("Something went wrong", msg_type="error")
        Send custom data
        >> cat.send_ws_message({"What day it is?": "It's my unbirthday"})
        """
        options = get_args(MSG_TYPES)

        if msg_type not in options:
            raise ValueError(
                f"The message type `{msg_type}` is not valid. Valid types: {', '.join(options)}"
            )

        if msg_type == "error":
            await self._send_ws_json(
                {"type": msg_type, "name": "GenericError", "description": str(content)}
            )
            return
        await self._send_ws_json({"type": msg_type, "content": content})

    async def send_chat_message(self, message: str | CatMessage):
        """
        Sends a chat message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged

        Args:
            message (str | CatMessage): message to send

        Examples
        --------
        Send a chat message during conversation from a hook, tool or form
        >> cat.send_chat_message("Hello, dear!")
        Using a `CatMessage` object
        >> message = CatMessage(text="Hello, dear!", user_id=cat.user.id)
        ... cat.send_chat_message(message)
        """
        if isinstance(message, str):
            message = CatMessage(text=message)

        await self._send_ws_json(message.model_dump())

    async def send_notification(self, content: str):
        """
        Sends a notification message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            content (str): message to send

        Examples
        --------
        Send a notification to the user
        >> cat.send_notification("It's late!")
        """
        await self.send_ws_message(content=content, msg_type="notification")

    async def send_error(self, error: str | Exception):
        """
        Sends an error message to the user using the active WebSocket connection.
        In case there is no connection, the message is skipped and a warning is logged.

        Args:
            error (Union[str, Exception]): message to send

        Examples
        --------
        Send an error message to the user
        >> cat.send_error("Something went wrong!")
        or
        >> cat.send_error(CustomException("Something went wrong!"))
        """
        if isinstance(error, str):
            error_message = {
                "type": "error",
                "name": "GenericError",
                "description": str(error),
            }
        else:
            error_message = {
                "type": "error",
                "name": error.__class__.__name__,
                "description": str(error),
            }

        await self._send_ws_json(error_message)

    async def llm(
        self,
        prompt: BasePromptTemplate,
        prompt_variables: Dict[str, Any] = None,
        procedures: List[CatProcedure] = None,
        stream: bool = False,
        **kwargs
    ) -> LLMAction:
        """
        Generate a response using the LLM model.
        This method is useful for generating a response with both a chat and a completion model using the same syntax.

        Args:
            prompt: str
                The prompt for generating the response.
            prompt_variables: Dict[str, Any]
                The inputs to be passed to the prompt template.
            procedures: List[CatProcedure], optional
                List of tools or forms to be used by the LLM.
            stream: bool, optional
                Whether to stream the tokens or not.

        Returns: The generated LLM response as an LLMAction, incorporating the textual result as well as the eventual
            tools called by the LLM.
        """
        # Add callbacks from plugins
        callbacks = ([] if not stream else [NewTokenHandler(self)])
        self.mad_hatter.execute_hook("llm_callbacks", callbacks, cat=self)

        procedures = (procedures or [])
        llm_to_use = self.large_language_model

        # Intrinsic detection of tool binding support
        should_bind_tools = False
        if procedures and hasattr(self.large_language_model, "bind_tools"):
            # Check if this is an Ollama model that might not support tools
            if hasattr(self.large_language_model, "_client"):
                supports_tools = (
                    hasattr(self.large_language_model, "format_tool_to_ollama") or
                    hasattr(self.large_language_model, "_convert_tools_to_ollama_tools") or
                    getattr(self.large_language_model, "supports_tool_calling", False)
                )

                # Additionally, check if the model has tool-related methods that indicate support
                tool_methods = [
                    method
                    for method in dir(self.large_language_model)
                    if "tool" in method.lower() and "support" in method.lower()
                ]

                should_bind_tools = supports_tools or len(tool_methods) > 0
            else:
                # For non-Ollama models, assume they support tool binding if they have the method
                should_bind_tools = True

        # Attempt tool binding only if intrinsically supported
        if should_bind_tools:
            try:
                llm_to_use = self.large_language_model.bind_tools(
                    [p.langchainfy() for p in procedures]
                )
            except Exception as e:
                model_id = getattr(self.large_language_model, "model", "unknown")
                log.warning(f"Tool binding failed for model {model_id} → running without procedures. Error: {e}")
        elif procedures:
            log.debug("Model does not intrinsically support procedures binding → skipping tools.")

        return_short = kwargs.pop("caller_return_short", False)
        skip = kwargs.pop("caller_skip", 2)
        caller = utils.get_caller_info(skip=skip, return_short=return_short)

        chain = (
            prompt
            | RunnableLambda(lambda x: log.langchain_log_prompt(x, f"{caller} prompt"))
            | llm_to_use
            | RunnableLambda(lambda x: log.langchain_log_output(x, f"{caller} prompt output"))
        )

        # in case we need to pass info to the template
        langchain_msg = await chain.ainvoke(prompt_variables or {}, config=RunnableConfig(callbacks=callbacks))
        langchain_msg_content = getattr(langchain_msg, "content", str(langchain_msg))

        if hasattr(langchain_msg, "tool_calls") and len(langchain_msg.tool_calls) > 0:
            return LLMAction(
                output=langchain_msg_content,
                tools=langchain_msg.tool_calls
            )

        # if no tools involved, just return the string
        return LLMAction(output=langchain_msg_content)

    async def __call__(self, user_message: UserMessage) -> CatMessage:
        """
        Run the conversation turn.

        This method is called on the user's message received from the client.

        Args:
            user_message: UserMessage
                Message received from the Websocket client.

        Returns:
            final_output: CatMessage
                Cat Message object, the Cat's answer to be sent to the client.

        Notes
        -----
        Here happens the main pipeline of the Cat. Namely, the Cat receives the user's input and recalls the memories.
        The retrieved context is formatted properly and given in input to the Agent that uses the LLM to produce the
        answer. This is formatted in a dictionary to be sent as a JSON via Websocket to the client.
        """
        # set up working memory for this convo turn
        # keeping track of model interactions
        self.working_memory.model_interactions = []
        # latest user message
        self.working_memory.user_message = user_message

        plugin_manager = self.plugin_manager

        # Run a totally custom reply (skips all the side effects of the framework)
        if fast_reply := plugin_manager.execute_hook("fast_reply", None, cat=self):
            return CatMessage(text=fast_reply)

        # hook to modify/enrich user input; this is the latest user message
        self.working_memory.user_message = utils.restore_original_model(
            plugin_manager.execute_hook("before_cat_reads_message", self.working_memory.user_message, cat=self),
            UserMessage
        )

        # reply with agent
        agent = CatAgent(self)
        try:
            agent_output = await agent.execute()
            if agent_output.output == utils.default_llm_answer_prompt():
                agent_output.with_llm_error = True
        except Exception as e:
            log.error(f"Agent id: {self.agent_id}. Error: {e}")
            agent_output = AgentOutput(
                output=f"An error occurred: {e}. Please, contact your support service.", with_llm_error=True
            )

        # prepare a final cat message
        final_output = CatMessage(text=agent_output.output)

        # run a message through plugins
        final_output = utils.restore_original_model(
            self.plugin_manager.execute_hook(
                "before_cat_sends_message", final_output, agent_output, cat=self
            ),
            CatMessage,
        )

        log.info(f"Agent id: {self.agent_id}. Agent output returned to stray:")
        log.info(agent_output)

        return final_output

    async def run_http(self, user_message: UserMessage) -> CatMessage:
        try:
            return await self(user_message)
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Agent id: {self.agent_id}. Error {e}")
            return CatMessage(text="", error=str(e))

    async def run_websocket(self, user_message: UserMessage) -> None:
        try:
            cat_message = await self(user_message)
            # send a message back to a client via WS
            await self.send_chat_message(cat_message)
        except Exception as e:
            # Log any unexpected errors
            log.error(f"Agent id: {self.agent_id}. Error {e}")
            try:
                # Send error as a websocket message
                await self.send_error(e)
            except ConnectionClosedOK as ex:
                log.warning(f"Agent id: {self.agent_id}. Warning {ex}")

    async def classify(
        self, sentence: str, labels: List[str] | Dict[str, List[str]], score_threshold: float = 0.5
    ) -> str | None:
        """
        Classify a sentence.

        Args:
            sentence: str
                Sentence to be classified.
            labels: List[str] or Dict[str, List[str]]
                Possible output categories and optional examples.
            score_threshold: float
                Threshold for the classification score. If the best match is below this threshold, returns None.

        Returns:
            label: str
                Sentence category.

        Examples
        -------
        >> await cat.classify("I feel good", labels=["positive", "negative"])
        "positive"

        Or giving examples for each category:

        >> example_labels = {
        ...     "positive": ["I feel nice", "happy today"],
        ...     "negative": ["I feel bad", "not my best day"],
        ... }
        ... await cat.classify("it is a bad day", labels=example_labels)
        "negative"
        """
        if isinstance(labels, Dict):
            labels_names = labels.keys()
            examples_list = "\n\nExamples:"
            examples_list += "".join([
                f'\n"{ex}" -> "{label}"' for label, examples in labels.items() for ex in examples
            ])
        else:
            labels_names = labels
            examples_list = ""

        labels_list = '"' + '", "'.join(labels_names) + '"'

        prompt = f"""Classify the provided sentence.

Allowed classes are:
{labels_list}{examples_list}

Just output the class, nothing else."""
        response = await self.llm(
            ChatPromptTemplate.from_messages([
                HumanMessagePromptTemplate.from_template(template=prompt)
            ]),
            prompt_variables={"input": sentence},
        )

        # find the closest match and its score with levenshtein distance
        best_label, score = min(
            ((label, utils.levenshtein_distance(response.output, label)) for label in labels_names),
            key=lambda x: x[1],
        )

        return best_label if score < score_threshold else None

    @property
    def lizard(self) -> BillTheLizard:
        """
        Instance of `BillTheLizard`. Use it to access the main components of the Cat.

        Returns:
            lizard: BillTheLizard
                Instance of langchain `BillTheLizard`.
        """
        return BillTheLizard()

    @property
    def websocket_manager(self) -> WebSocketManager:
        """
        Instance of `WebsocketManager`. Use it to access the manager of the Websocket connections.

        Returns:
            websocket_manager: WebsocketManager
                Instance of `WebsocketManager`.
        """
        return self.lizard.websocket_manager

    @property
    def cheshire_cat(self) -> "CheshireCat":
        """
        Instance of langchain `CheshireCat`. Use it to access the main components of the chatbot.

        Returns:
            cheshire_cat: CheshireCat
                Instance of `CheshireCat`.
        """
        return self.lizard.get_cheshire_cat(self.agent_id)

    @property
    def large_language_model(self) -> BaseLanguageModel:
        """
        Instance of langchain `LLM`.
        Only use it if you directly want to deal with langchain, prefer method `stray.llm(prompt)` otherwise.
        """
        return self.cheshire_cat.large_language_model

    @property
    def embedder(self) -> Embeddings:
        """
        Langchain `Embeddings` object.
        Returns:
            embedder: Langchain `Embeddings`
                Langchain embedder to turn text into a vector.

        Examples
        --------
        >> cat.embedder.embed_query("Oh dear!")
        [0.2, 0.02, 0.4, ...]
        """
        return self.lizard.embedder

    @property
    def rabbit_hole(self) -> RabbitHole:
        """
        Gives access to the `RabbitHole`, to upload documents and URLs into the vector DB.

        Returns:
            rabbit_hole: RabbitHole
            Module to ingest documents and URLs for RAG.
        Examples
        --------
        >> cat.rabbit_hole.ingest_file(...)
        """
        return self.lizard.rabbit_hole

    @property
    def plugin_manager(self) -> Tweedledee:
        """
        Gives access to the `Tweedledee` plugin manager. Use it to manage plugins and hooks.
        Returns:
            plugin_manager: Tweedledee
                Plugin manager of the Cat.
        """
        return self.cheshire_cat.plugin_manager

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
        >> cat.mad_hatter.get_plugin().path
        /app/plugins/my_plugin
        Obtain plugin settings
        >> cat.mad_hatter.get_plugin().load_settings()
        {"num_cats": 44, "rows": 6, "remainder": 0}
        """
        return self.plugin_manager

    @property
    def white_rabbit(self) -> WhiteRabbit:
        """
        Gives access to `WhiteRabbit`, to schedule repeatable tasks.

        Returns:
            white_rabbit: WhiteRabbit
                Module to manage cron tasks via `APScheduler`.

        Examples
        --------
        Send a websocket message after 30 seconds
        >> def ring_alarm_api():
        ...     cat.send_chat_message("It's late!")
        ...
        ... cat.white_rabbit.schedule_job(ring_alarm_api, seconds=30)
        """
        return WhiteRabbit()

    # each time we access the file handlers, plugins can intervene
    @property
    def file_handlers(self) -> Dict:
        return self.cheshire_cat.file_handlers

    # each time we access the text splitter, plugins can intervene
    @property
    def text_splitter(self):
        return self.cheshire_cat.chunker
