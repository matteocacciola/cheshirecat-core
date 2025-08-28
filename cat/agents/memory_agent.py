from langchain.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import SystemMessagePromptTemplate, HumanMessagePromptTemplate

from cat import utils
from cat.agents.base_agent import BaseAgent, AgentOutput


class MemoryAgent(BaseAgent):
    def execute(self, *args, **kwargs) -> AgentOutput:
        prompt_template = kwargs.get("prompt", "")

        # Prepare the input variables
        prompt_variables = {
            "context": self._stray.working_memory.agent_input.context,
            "tools_output": self._stray.working_memory.agent_input.tools_output,
        }

        # Ensure prompt inputs and prompt placeholders map
        prompt_variables, prompt_template = utils.match_prompt_variables(
            prompt_variables, prompt_template
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(template=prompt_template),
                *self._stray.working_memory.agent_input.history,
                HumanMessagePromptTemplate.from_template("{input}"),
            ]
        )
        prompt_variables["input"] = self._stray.working_memory.agent_input.input

        # Format the prompt template with the actual values to get a string
        # Convert to string - this will combine all messages into a single string
        output = self._stray.llm(
            prompt,
            inputs=prompt_variables,
            stream=True,
            caller_return_short=True,
            caller_skip=2,
        )

        return AgentOutput(output=output)
