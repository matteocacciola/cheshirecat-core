import random
from typing import Dict, Any
from langchain.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import SystemMessagePromptTemplate

from cat.agents.base_agent import BaseAgent, AgentOutput
from cat.agents.form_agent import FormAgent
from cat.looking_glass import prompts
from cat.looking_glass.output_parser import ChooseProcedureOutputParser, LLMAction
from cat.experimental.form.cat_form import CatForm
from cat.mad_hatter.decorators import CatTool
from cat.mad_hatter.plugin import Plugin
from cat.log import log
from cat import utils


class ProceduresAgent(BaseAgent):
    allowed_procedures: Dict[str, CatTool | CatForm] = {}

    def __init__(self, stray):
        super().__init__(stray)
        self._form_agent = FormAgent(self._stray)

    def execute(self, *args, **kwargs) -> AgentOutput:
        # run active form if present
        form_output = self._form_agent.execute()
        if form_output.return_direct:
            return form_output

        # Select and run useful procedures
        procedural_memories = self._stray.working_memory.procedural_memories
        if len(procedural_memories) > 0:
            log.debug(f"Procedural memories retrieved: {len(procedural_memories)}.")

            try:
                procedures_result = self.execute_procedures()
                if procedures_result.return_direct:
                    # exit agent if a return_direct procedure was executed
                    return procedures_result

                # store intermediate steps to enrich memory chain
                intermediate_steps = procedures_result.intermediate_steps

                # Adding the tools_output key in agent input, needed by the memory chain
                if len(intermediate_steps) > 0:
                    self._stray.working_memory.agent_input.tools_output = "## Context of executed system tools: \n"
                    self._stray.working_memory.agent_input.tools_output += " - ".join([
                        f"{proc_res[0][0]}: {proc_res[1]}\n" for proc_res in intermediate_steps
                    ])
                return procedures_result
            except Exception as e:
                log.error(f"Error while executing procedures: {e}")

        return AgentOutput()

    def execute_procedures(self) -> AgentOutput:
        """
        Execute procedures.

        Returns:
            AgentOutput instance
        """
        plugin_manager = self._stray.cheshire_cat.plugin_manager

        # get procedures prompt from plugins
        procedures_prompt_template = plugin_manager.execute_hook(
            "agent_prompt_instructions", prompts.TOOL_PROMPT, cat=self._stray
        )

        # Gather recalled procedures
        recalled_procedures_names = {
            p.document.metadata["source"] for p in self._stray.working_memory.procedural_memories if
            p.document.metadata["type"] in ["tool", "form"] and p.document.metadata["trigger_type"] in [
                "description", "start_example"
            ]
        }
        recalled_procedures_names = plugin_manager.execute_hook(
            "agent_allowed_tools", recalled_procedures_names, cat=self._stray
        )

        # Prepare allowed procedures (tools instances and form classes)
        allowed_procedures = {p.name: p for p in plugin_manager.procedures if p.name in recalled_procedures_names}

        # Execute chain and obtain a choice of procedure from the LLM
        llm_action = self.execute_chain(procedures_prompt_template, allowed_procedures)

        # route execution to sub-agents
        if not llm_action.action:
            return AgentOutput(output="")

        # execute chosen tool / form
        # loop over allowed tools and forms
        chosen_procedure = allowed_procedures.get(llm_action.action, None)
        try:
            if Plugin.is_cat_tool(chosen_procedure):
                # execute tool
                tool_output = chosen_procedure.run(llm_action.action_input, stray=self._stray)
                return AgentOutput(
                    output=tool_output,
                    return_direct=chosen_procedure.return_direct,
                    intermediate_steps=[
                        ((llm_action.action, llm_action.action_input), tool_output)
                    ]
                )
            if Plugin.is_cat_form(chosen_procedure):
                # create form
                form_instance = chosen_procedure(self._stray)
                # store active form in working memory
                self._stray.working_memory.active_form = form_instance
                # execute form
                return self._form_agent.execute(self._stray)
        except Exception as e:
            log.error(f"Error executing {chosen_procedure.procedure_type} `{chosen_procedure.name}`: {e}")

        return AgentOutput(output="")

    def execute_chain(
        self, procedures_prompt_template: Any, allowed_procedures: Dict[str, CatTool | CatForm]
    ) -> LLMAction:
        """
        Execute the chain to choose a procedure.
        Args:
            procedures_prompt_template: Any
            allowed_procedures: Dict[str, CatTool | CatForm]

        Returns:
            LLMAction instance
        """
        # Prepare info to fill up the prompt
        prompt_variables = {
            "tools": "\n".join(
                f'- "{tool.name}": {tool.description}'
                for tool in allowed_procedures.values()
            ),
            "tool_names": '"' + '", "'.join(allowed_procedures.keys()) + '"',
            "examples": self.generate_examples(allowed_procedures),
        }

        # Ensure prompt inputs and prompt placeholders map
        prompt_variables, procedures_prompt_template = utils.match_prompt_variables(
            prompt_variables, procedures_prompt_template
        )

        # Generate prompt
        prompt = ChatPromptTemplate(
            [
                SystemMessagePromptTemplate.from_template(template=procedures_prompt_template),
                *self._stray.working_memory.agent_input.history,
            ]
        )

        # Format the prompt template with the actual values to get a string
        # Convert to string - this will combine all messages into a single string
        llm_action: LLMAction = self._stray.llm(
            prompt,
            inputs=prompt_variables,
            output_parser=ChooseProcedureOutputParser(), # ensures output is a LLMAction
            caller_return_short=True,
            caller_skip=2,
        )

        return llm_action

    def generate_examples(self, allowed_procedures: Dict[str, CatTool | CatForm]) -> str:
        def get_example(proc):
            example_json = f"""
{{
    "action": "{proc.name}",
    "action_input": "...input here..."
}}"""
            result = f"\nQuestion: {random.choice(proc.start_examples)}"
            result += f"\n```json\n{example_json}\n```"
            result += """
Question: I have no questions
```json
{
    "action": "no_answer",
    "action_input": null
}
```"""
            return result

        list_examples = [get_example(proc) for proc in allowed_procedures.values() if proc.start_examples]

        return "## Here some examples:\n" + "".join(list_examples) if list_examples else ""
