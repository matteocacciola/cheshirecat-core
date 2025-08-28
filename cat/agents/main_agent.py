from cat.agents import AgentInput, AgentOutput, BaseAgent
from cat.agents.memory_agent import MemoryAgent
from cat.agents.procedures_agent import ProceduresAgent
from cat.looking_glass import prompts
from cat.utils import restore_original_model
from cat.env import get_env


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

        plugin_manager = self._stray.cheshire_cat.plugin_manager

        agent_input = AgentInput(
            context=[m.document for m in self._stray.working_memory.declarative_memories],
            input=self._stray.working_memory.user_message.text,
            history=[h.langchainfy() for h in self._stray.working_memory.history[-latest_n_history:]]
        )
        agent_input = restore_original_model(
            plugin_manager.execute_hook("before_agent_starts", agent_input, cat=self._stray), AgentInput
        )

        # store the agent input inside the working memory
        self._stray.working_memory.agent_input = agent_input

        # should we run the default agents?
        agent_fast_reply = restore_original_model(
            plugin_manager.execute_hook("agent_fast_reply", {}, cat=self._stray),
            AgentOutput
        )
        if agent_fast_reply and agent_fast_reply.output:
            return agent_fast_reply

        # run tools and forms
        procedures_agent = ProceduresAgent(self._stray)
        procedures_agent_out = procedures_agent.execute()
        if procedures_agent_out.return_direct:
            return procedures_agent_out

        # obtain prompt parts from plugins
        prompt = plugin_manager.execute_hook("agent_prompt", prompts.MAIN_PROMPT, cat=self._stray)

        # we run memory agent if:
        # - no procedures were recalled or selected or
        # - procedures have all return_direct=False
        memory_agent = MemoryAgent(self._stray)
        memory_agent_out = memory_agent.execute(prompt=prompt)

        memory_agent_out.intermediate_steps += procedures_agent_out.intermediate_steps

        return memory_agent_out
