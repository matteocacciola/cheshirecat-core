import re
from abc import ABC, abstractmethod
from typing import Type, List, Dict, Any, Tuple
from langchain_classic.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool
from pydantic import ConfigDict, BaseModel

from cat.log import log
from cat.looking_glass.models import AgentOutput
from cat.services.factory.models import BaseFactoryConfigModel


class AgenticTask(BaseModel):
    prompt: ChatPromptTemplate
    prompt_variables: Dict[str, Any] | None = None
    tools: List[StructuredTool] | None = None


class BaseAgenticWorkflowHandler(ABC):
    """
    Base class to build custom Agentic Workflow.
    MUST be implemented by subclasses.
    """
    def __init__(self):
        self._task: AgenticTask | None = None
        self._llm: BaseLanguageModel | None = None
        self._callbacks: List[BaseCallbackHandler] | None = None
        self._can_bind_tools = False

    def _bootstrap(self, task: AgenticTask, llm: BaseLanguageModel, callbacks: List[BaseCallbackHandler] = None):
        self._task = task
        self._llm = llm
        self._callbacks = callbacks or []

        # Intrinsic detection of tool binding support
        self._can_bind_tools = task.tools and hasattr(llm, "bind_tools")

    async def run(
        self, task: AgenticTask, llm: BaseLanguageModel, callbacks: List[BaseCallbackHandler] = None
    ) -> AgentOutput:
        """
        Executes the agent with the given prompt and procedures. It processes the LLM output, handles tool
        calls, and generates the final response. It also cleans the response from any tags.

        Args:
            task (AgenticTask): The agentic task containing prompt, variables, and tools.
            llm (BaseLanguageModel): The language model to use for generating responses.
            callbacks (List[BaseCallbackHandler], optional):  List of callback handlers for logging and monitoring, by default None.

        Returns:
            AgentOutput
                The final output from the agent, including text and any actions taken.
        """
        from cat.looking_glass.callbacks import LoggingCallbackHandler

        callbacks = callbacks or []
        callbacks.append(LoggingCallbackHandler())

        self._bootstrap(task, llm, callbacks)

        result = await self._run()
        return result

    @abstractmethod
    async def _run(self) -> AgentOutput:
        """
        The internal run method to be implemented by subclasses.
        Executes the agentic workflow logic.
        """
        pass


class CoreAgenticWorkflow(BaseAgenticWorkflowHandler):
    async def _run(self) -> AgentOutput:
        def clean_response(response: str) -> str:
            # parse the `response` string and get the text from <answer></answer> tag
            if "<answer>" in response and "</answer>" in response:
                start = response.index("<answer>") + len("<answer>")
                end = response.index("</answer>")
                return response[start:end].strip()
            # otherwise, remove from `response` all the text between whichever tag and then return the remaining string
            # This pattern matches any complete tag pair: <tagname>content</tagname>
            cleaned = re.sub(r'<([^>]+)>.*?</\1>', '', response, flags=re.DOTALL)
            return cleaned.strip()

        def extract_info(action) -> Tuple[Tuple[str | None, Dict, Dict] | None, str]:
            if not isinstance(action, tuple) or len(action) < 2:
                return None, str(action)
            # Extract the main fields from the first element of the tuple
            tool = getattr(action[0], "tool")
            tool_input = getattr(action[0], "tool_input", {})
            usage_metadata = getattr(action[0], "usage_metadata", {})
            # Create a tuple with the extracted information
            return (tool, tool_input, usage_metadata), action[1]

        # Direct LLM invocation
        if not self._can_bind_tools:
            prompt_variables = self._task.prompt_variables or {}

            chain = self._task.prompt | self._llm
            langchain_msg = await chain.ainvoke(prompt_variables, config=RunnableConfig(callbacks=self._callbacks))

            output = getattr(langchain_msg, "content", str(langchain_msg))
            return AgentOutput(output=clean_response(output))

        try:
            self._task.prompt.messages.append(HumanMessagePromptTemplate.from_template("{agent_scratchpad}"))

            # Create the agent with proper prompt structure
            agent = create_tool_calling_agent(llm=self._llm, tools=self._task.tools, prompt=self._task.prompt)
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

            cleaned_output = clean_response(langchain_msg.get("output", "")).strip()
            extracted_steps = [extract_info(step) for step in langchain_msg.get("intermediate_steps", [])]
            return AgentOutput(output=cleaned_output, intermediate_steps=extracted_steps)
        except Exception as e:
            log.warning(f"Tool binding failed with error: {e}. Falling back to direct LLM invocation.")
            self._can_bind_tools = False

            res = await self._run()
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
