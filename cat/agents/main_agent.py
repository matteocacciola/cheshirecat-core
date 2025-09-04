from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate

from cat.agents.base_agent import CatAgent, AgentInput, AgentOutput
from cat.env import get_env


class DefaultAgent(CatAgent):
    """Default Agent, which uses the LLM."""
    def __init__(self, stray):
        super().__init__(stray)

        self.verbose = False
        if get_env("CCAT_LOG_LEVEL").lower() in ["debug", "info"]:
            self.verbose = True

    async def execute_llm(self, agent_input: AgentInput) -> AgentOutput:
        # obtain prompt parts from plugins
        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(template=self._get_system_prompt()),
                *agent_input.history,
            ]
        )

        # Format the prompt template with the actual values to get a string
        # Convert to string - this will combine all messages into a single string
        llm_output = await self._stray.llm(
            prompt,
            prompt_variables={"context": agent_input.context, "input": agent_input.input},
            procedures=self._get_procedures(),
            stream=True,
            caller_return_short=True,
            caller_skip=2,
        )

        return llm_output
