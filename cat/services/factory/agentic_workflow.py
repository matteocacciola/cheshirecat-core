import re
from abc import ABC, abstractmethod
from typing import Type, List, Dict, Tuple
from langchain_classic.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, SystemMessagePromptTemplate
from langchain_core.runnables import RunnableConfig
from pydantic import ConfigDict

from cat.log import log
from cat.looking_glass.models import AgenticWorkflowOutput, AgenticWorkflowTask
from cat.services.factory.models import BaseFactoryConfigModel
from cat.services.factory.vector_db import BaseVectorDatabaseHandler
from cat.services.memory.models import VectorMemoryType, DocumentRecall, RecallSettings


class BaseAgenticWorkflowHandler(ABC):
    """
    Base class to build a custom Agentic Workflow.
    MUST be implemented by subclasses.

    Attributes
    ----------
    _vector_memory_handler: BaseVectorDatabaseHandler
        The vector memory handler to manage vector database operations.
    """
    def __init__(self):
        self._vector_memory_handler = None

        self._task: AgenticWorkflowTask | None = None
        self._llm: BaseLanguageModel | None = None
        self._callbacks: List[BaseCallbackHandler] | None = None
        self._can_bind_tools = False

    @property
    def vector_memory_handler(self) -> BaseVectorDatabaseHandler:
        return self._vector_memory_handler

    @vector_memory_handler.setter
    def vector_memory_handler(self, vmh: BaseVectorDatabaseHandler):
        self._vector_memory_handler = vmh

    async def run(
        self, task: AgenticWorkflowTask, llm: BaseLanguageModel, callbacks: List[BaseCallbackHandler] = None
    ) -> AgenticWorkflowOutput:
        """
        Executes the agent with the given prompt and procedures. It processes the LLM output, handles tool
        calls, and generates the final response. It also cleans the response from any tags.

        Args:
            task (AgenticWorkflowTask): The input containing the task details.
            llm (BaseLanguageModel): The language model to use for generating responses.
            callbacks (List[BaseCallbackHandler], optional): List of callback handlers for logging and monitoring, by default None.

        Returns:
            AgentOutput
                The final output from the agent, including text and any actions taken.
        """
        from cat.looking_glass.callbacks import LoggingCallbackHandler

        callbacks = callbacks or []
        callbacks.append(LoggingCallbackHandler())

        self._task = task
        self._llm = llm
        self._callbacks = callbacks or []

        prompt = ChatPromptTemplate.from_messages([
            *([SystemMessagePromptTemplate.from_template(template=task.system_prompt)] if task.system_prompt else []),
            HumanMessagePromptTemplate.from_template(template=task.user_prompt),
            *self._task.history,
        ])

        # Intrinsic detection of tool binding support
        self._can_bind_tools = task.tools and hasattr(llm, "bind_tools")

        result = await self._run(prompt)
        return result

    @abstractmethod
    async def context_retrieval(
        self,
        collection: VectorMemoryType,
        params: RecallSettings,
    ) -> List[DocumentRecall]:
        """
        Abstract method to recall relevant documents from a specified vector memory
        collection based on the given query vector. This method operates asynchronously.

        Args:
            collection (VectorMemoryType): The collection from which documents will be recalled.
            params (RecallSettings): The settings containing the query vector and other recall parameters.

        Returns:
            List[DocumentRecall]: A list of recalled documents along with their similarity scores.
        """
        pass

    @abstractmethod
    async def _run(self, prompt: ChatPromptTemplate) -> AgenticWorkflowOutput:
        """
        The internal run method to be implemented by subclasses.
        Executes the agentic workflow logic.

        Args:
            prompt (ChatPromptTemplate): The prompt template to use for the agent.

        Returns:
            AgenticWorkflowOutput: The output of the agentic workflow execution.
        """
        pass


class CoreAgenticWorkflow(BaseAgenticWorkflowHandler):
    async def context_retrieval(
        self,
        collection: VectorMemoryType,
        params: RecallSettings,
    ) -> List[DocumentRecall]:
        if params.k:
            memories = await self.vector_memory_handler.recall_tenant_memory_from_embedding(
                str(collection), params.embedding, params.metadata, params.k, params.threshold
            )
            return memories

        memories = await self.vector_memory_handler.recall_tenant_memory(str(collection))
        return memories

    def _clean_response(self, response: str) -> str:
        # parse the `response` string and get the text from <answer></answer> tag
        if "<answer>" in response and "</answer>" in response:
            start = response.index("<answer>") + len("<answer>")
            end = response.index("</answer>")
            return response[start:end].strip()

        # otherwise, remove from `response` all the text between whichever tag and then return the remaining string
        # This pattern matches any complete tag pair: <tagname>content</tagname>
        cleaned = re.sub(r'<([^>]+)>.*?</\1>', '', response, flags=re.DOTALL)
        return cleaned.strip()

    def _extract_info(self, action) -> Tuple[Tuple[str | None, Dict, Dict] | None, str]:
        if not isinstance(action, tuple) or len(action) < 2:
            return None, str(action)

        # Extract the main fields from the first element of the tuple
        tool = getattr(action[0], "tool")
        tool_input = getattr(action[0], "tool_input", {})
        usage_metadata = getattr(action[0], "usage_metadata", {})

        # Create a tuple with the extracted information
        return (tool, tool_input, usage_metadata), action[1]

    async def _run_no_bind(self, prompt: ChatPromptTemplate) -> AgenticWorkflowOutput:
        prompt_variables = self._task.prompt_variables or {}

        chain = prompt | self._llm
        langchain_msg = await chain.ainvoke(prompt_variables, config=RunnableConfig(callbacks=self._callbacks))

        output = getattr(langchain_msg, "content", str(langchain_msg))
        return AgenticWorkflowOutput(output=self._clean_response(output))

    async def _run_with_bind(self, prompt: ChatPromptTemplate) -> AgenticWorkflowOutput:
        # Deepcopy the prompt to avoid modifying the original
        prompt = ChatPromptTemplate.from_messages(
            prompt.messages + [HumanMessagePromptTemplate.from_template("{agent_scratchpad}")]
        )

        # Create the agent with the proper prompt structure
        agent = create_tool_calling_agent(llm=self._llm, tools=self._task.tools, prompt=prompt)
        # Create the agent executor
        agent_executor = AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=self._task.tools,
            callbacks=self._callbacks,
            return_intermediate_steps=True,
            verbose=True,
            handle_parsing_errors=True,  # Add error handling
        )
        # Run the agent
        langchain_msg = await agent_executor.ainvoke(
            self._task.prompt_variables or {}, config=RunnableConfig(callbacks=self._callbacks)
        )

        cleaned_output = self._clean_response(langchain_msg.get("output", "")).strip()
        extracted_steps = [self._extract_info(step) for step in langchain_msg.get("intermediate_steps", [])]
        return AgenticWorkflowOutput(output=cleaned_output, intermediate_steps=extracted_steps)

    async def _run(self, prompt: ChatPromptTemplate) -> AgenticWorkflowOutput:
        # Direct LLM invocation
        if not self._can_bind_tools:
            res = await self._run_no_bind(prompt)
            return res

        try:
            res = await self._run_with_bind(prompt)
            return res
        except Exception as e:
            log.warning(f"Tool binding failed with error: {e}. Falling back to direct LLM invocation.")

            res = await self._run_no_bind(prompt)
            return res


class AgenticWorkflowConfig(BaseFactoryConfigModel, ABC):
    @classmethod
    def base_class(cls) -> Type[BaseAgenticWorkflowHandler]:
        return BaseAgenticWorkflowHandler

    @classmethod
    @abstractmethod
    def pyclass(cls) -> Type[BaseAgenticWorkflowHandler]:
        pass


class CoreAgenticWorkflowConfig(AgenticWorkflowConfig):
    model_config = ConfigDict(
        json_schema_extra={
            "humanReadableName": "Single-agent Workflow",
            "description": "Core built-in single-agent workflow.",
            "link": "",
        }
    )

    @classmethod
    def pyclass(cls) -> Type[CoreAgenticWorkflow]:
        return CoreAgenticWorkflow
