import re
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate

from cheshirecat import utils
from cheshirecat.agents.base_agent import AgentInput, AgentOutput, BaseAgent, LLMAction
from cheshirecat.env import get_env
from cheshirecat.utils import dispatch_event


class MainAgent(BaseAgent):
    """Main Agent. This class manages sub agents that in turn use the LLM."""
    def __init__(self, stray):
        super().__init__(stray)

        self.verbose = False
        if get_env("CCAT_LOG_LEVEL").lower() in ["debug", "info"]:
            self.verbose = True

    async def execute(self, *args, **kwargs) -> AgentOutput:
        def clean(response: str) -> str:
            # parse the `response` string and get the text from <answer></answer> tag
            if "<answer>" in response and "</answer>" in response:
                start = response.index("<answer>") + len("<answer>")
                end = response.index("</answer>")
                return response[start:end].strip()
            # otherwise, remove from `response` all the text between whichever tag and then return the remaining string
            # This pattern matches any complete tag pair: <tagname>content</tagname>
            cleaned = re.sub(r'<([^>]+)>.*?</\1>', '', response, flags=re.DOTALL)
            return cleaned.strip()

        # prepare input to be passed to the agent.
        #   Info will be extracted from working memory
        # Note: agent_input works both as a dict and as an object
        latest_n_history = kwargs.get("latest_n_history", 5) * 2  # each interaction has user + cat message

        agent_input = AgentInput(
            context=[m.document for m in self._stray.working_memory.declarative_memories],
            input=self._stray.working_memory.user_message.text,
            history=[h.langchainfy() for h in self._stray.working_memory.history[-latest_n_history:]]
        )
        agent_input = utils.restore_original_model(
            self._plugin_manager.execute_hook("before_agent_starts", agent_input, cat=self._stray), AgentInput
        )

        # should we run the default agents?
        agent_fast_reply = utils.restore_original_model(
            self._plugin_manager.execute_hook("agent_fast_reply", {}, cat=self._stray),
            AgentOutput
        )
        if agent_fast_reply and agent_fast_reply.output:
            return agent_fast_reply

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
            tools=self._get_tools(),
            forms=self._get_forms(),
            stream=True,
            caller_return_short=True,
            caller_skip=2,
        )

        if type(llm_output) is str:
            # simple string message
            return AgentOutput(output=clean(llm_output))

        if type(llm_output) is LLMAction:
            tools_forms = self._get_tools() + self._get_forms()

            # LLM has chosen a tool or a form, run it to get the output
            for t_or_f in tools_forms:
                if t_or_f.name == llm_output.name:
                    # update the action with an output, actually executing the tool / form
                    llm_output = dispatch_event(
                        t_or_f.execute(self._stray, llm_output)
                    )

            return AgentOutput(output=llm_output.output, actions=[llm_output])

        return AgentOutput()
