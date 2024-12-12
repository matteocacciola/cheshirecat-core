import time
from typing import List
from datetime import timedelta

from cat.agents import AgentInput, AgentOutput, BaseAgent
from cat.agents.memory_agent import MemoryAgent
from cat.agents.procedures_agent import ProceduresAgent
from cat.looking_glass import prompts
from cat.memory.vector_memory_collection import DocumentRecall
from cat.utils import verbal_timedelta, restore_original_model
from cat.env import get_env


class MainAgent(BaseAgent):
    """Main Agent. This class manages sub agents that in turn use the LLM."""

    def __init__(self):
        self.verbose = False
        if get_env("CCAT_LOG_LEVEL") in ["DEBUG", "INFO"]:
            self.verbose = True

    def execute(self, stray, *args, **kwargs) -> AgentOutput:
        # prepare input to be passed to the agent.
        #   Info will be extracted from working memory
        # Note: agent_input works both as a dict and as an object
        plugin_manager = stray.cheshire_cat.plugin_manager

        agent_input = self.format_agent_input(stray)
        agent_input = restore_original_model(
            plugin_manager.execute_hook("before_agent_starts", agent_input, cat=stray), AgentInput
        )

        # store the agent input inside the working memory
        stray.working_memory.agent_input = agent_input

        # should we run the default agents?
        agent_fast_reply = restore_original_model(
            plugin_manager.execute_hook("agent_fast_reply", {}, cat=stray),
            AgentOutput
        )
        if agent_fast_reply and agent_fast_reply.output:
            return agent_fast_reply

        # obtain prompt parts from plugins
        prompt_prefix = plugin_manager.execute_hook(
            "agent_prompt_prefix", prompts.MAIN_PROMPT_PREFIX, cat=stray
        )
        prompt_suffix = plugin_manager.execute_hook(
            "agent_prompt_suffix", prompts.MAIN_PROMPT_SUFFIX, cat=stray
        )

        # run tools and forms
        procedures_agent = ProceduresAgent()
        procedures_agent_out: AgentOutput = procedures_agent.execute(stray)
        if procedures_agent_out.return_direct:
            return procedures_agent_out

        # we run memory agent if:
        # - no procedures were recalled or selected or
        # - procedures have all return_direct=False
        memory_agent = MemoryAgent()
        memory_agent_out: AgentOutput = memory_agent.execute(
            # TODO: should all agents only receive stray?
            stray, prompt_prefix=prompt_prefix, prompt_suffix=prompt_suffix
        )

        memory_agent_out.intermediate_steps += procedures_agent_out.intermediate_steps

        return memory_agent_out

    def format_agent_input(self, stray: "StrayCat") -> AgentInput:
        """Format the input for the Agent.

        The method formats the strings of recalled memories and chat history that will be provided to the Langchain
        Agent and inserted in the prompt.

        Args:
            stray: StrayCat
                Stray Cat instance containing the working memory and the chat history.

        Returns:
            AgentInput
                Formatted output to be parsed by the Agent executor. Works both as a dictionary and as an object.

        See Also:
            MainAgent.agent_prompt_episodic_memories
            MainAgent.agent_prompt_declarative_memories

        Notes
        -----
        The context of memories and conversation history is properly formatted before being parsed by the and, hence,
        information are inserted in the main prompt.
        All the formatting pipeline is hookable and memories can be edited.
        """

        # format memories to be inserted in the prompt
        episodic_memory_formatted_content = self.agent_prompt_episodic_memories(
            stray.working_memory.episodic_memories
        )
        declarative_memory_formatted_content = self.agent_prompt_declarative_memories(
            stray.working_memory.declarative_memories
        )

        # format conversation history to be inserted in the prompt
        # TODO V2: take away
        conversation_history_formatted_content = stray.working_memory.stringify_chat_history()

        return AgentInput(
            episodic_memory=episodic_memory_formatted_content,
            declarative_memory=declarative_memory_formatted_content,
            tools_output="",
            input=stray.working_memory.user_message.text,  # TODO V2: take away
            chat_history=conversation_history_formatted_content, # TODO V2: take away
        )

    def agent_prompt_episodic_memories(self, memory_docs: List[DocumentRecall]) -> str:
        """Formats episodic memories to be inserted into the prompt.

        Args:
            memory_docs: List[DocumentRecall]

        Returns:
            memory_content: str
                String of retrieved context from the episodic memory.
        """

        # convert docs to simple text
        memory_texts = [m.document.page_content.replace("\n", ". ") for m in memory_docs]

        # add time information (e.g. "2 days ago")
        # Get Time information in the Document metadata
        # Get Current Time - Time when memory was stored
        # Convert and Save timestamps to Verbal (e.g. "2 days ago")
        memory_timestamps = [
            f" ({verbal_timedelta(timedelta(seconds=(time.time() - m.document.metadata['when'])))})" for m in memory_docs
        ]

        # Join Document text content with related temporal information
        memory_texts = [a + b for a, b in zip(memory_texts, memory_timestamps)]

        # Format the memories for the output
        memories_separator = "\n  - "
        memory_content = (
            "## Context of things the Human said in the past: "
            + memories_separator
            + memories_separator.join(memory_texts)
        )

        # if no data is retrieved from memory don't erite anithing in the prompt
        if len(memory_texts) == 0:
            memory_content = ""

        return memory_content

    def agent_prompt_declarative_memories(self, memory_docs: List[DocumentRecall]) -> str:
        """Formats the declarative memories for the prompt context.
        Such context is placed in the `agent_prompt_prefix` in the place held by {declarative_memory}.

        Args:
            memory_docs: List[DocumentRecall]

        Returns:
            memory_content: str
                String of retrieved context from the declarative memory.
        """

        # convert docs to simple text
        memory_texts = [m.document.page_content.replace("\n", ". ") for m in memory_docs]

        # add source information (e.g. "extracted from file.txt")
        # Get and save the source of the memory
        memory_sources = [f" (extracted from {m.document.metadata['source']})" for m in memory_docs]
        # Join Document text content with related source information
        memory_texts = [a + b for a, b in zip(memory_texts, memory_sources)]

        # if no data is retrieved from memory don't write anything in the prompt
        if len(memory_texts) == 0:
            return ""

        # Format the memories for the output
        memories_separator = "\n  - "

        return (
            "## Context of documents containing relevant information: "
            + memories_separator
            + memories_separator.join(memory_texts)
        )
