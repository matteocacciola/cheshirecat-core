from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate

from cheshirecat import utils
from cheshirecat.agents.base_agent import AgentInput, AgentOutput, BaseAgent, LLMAction
from cheshirecat.looking_glass import prompts
from cheshirecat.env import get_env


class MainAgent(BaseAgent):
    """Main Agent. This class manages sub agents that in turn use the LLM."""
    def __init__(self, stray):
        super().__init__(stray)

        self.verbose = False
        if get_env("CCAT_LOG_LEVEL").lower() in ["debug", "info"]:
            self.verbose = True

    def execute(self, *args, **kwargs) -> AgentOutput:
        # prepare input to be passed to the agent.
        #   Info will be extracted from working memory
        # Note: agent_input works both as a dict and as an object
        latest_n_history = kwargs.get("latest_n_history", 5)

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
        prompt = self._plugin_manager.execute_hook("agent_system_prompt", prompts.MAIN_PROMPT, cat=self._stray)

        # we run memory agent if:
        # - no procedures were recalled or selected or
        # - procedures have all return_direct=False
        prompt_variables = {"context": agent_input.context}

        # Ensure prompt inputs and prompt placeholders map
        prompt_variables, prompt_template = utils.match_prompt_variables(
            prompt_variables, prompt
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                SystemMessagePromptTemplate.from_template(template=prompt_template),
                *agent_input.history,
                HumanMessagePromptTemplate.from_template("{input}"),
            ]
        )
        prompt_variables["input"] = agent_input.input

        # Format the prompt template with the actual values to get a string
        # Convert to string - this will combine all messages into a single string
        llm_output = self._stray.llm(
            prompt,
            prompt_variables=prompt_variables,
            tools=self._get_tools(),
            stream=True,
            caller_return_short=True,
            caller_skip=2,
        )

        if type(llm_output) is str:
            # simple string message
            return AgentOutput(output=llm_output)

        if type(llm_output) is LLMAction:
            # LLM has chosen a tool, run it to get the output
            for t in self._get_tools():
                if t.name == llm_output.name:
                    # update the action with an output, actually executing the tool
                    llm_output = t.execute(self._stray, llm_output)

            return AgentOutput(output=llm_output.output, actions=[llm_output])

        return AgentOutput()
