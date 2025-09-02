from cheshirecat.agents.base_agent import BaseAgent, AgentOutput
from cheshirecat.experimental.form.cat_form import CatFormState
from cheshirecat.log import log


class FormAgent(BaseAgent):
    def execute(self, *args, **kwargs) -> AgentOutput:
        # get active form from working memory
        active_form = self._stray.working_memory.active_form
        
        if not active_form:
            # no active form
            return AgentOutput()

        if active_form.state == CatFormState.CLOSED:
            # form is closed, delete it from working memory
            self._stray.working_memory.active_form = None
            return AgentOutput()

        # continue form
        try:
            form_output = active_form.next() # form should be async and should be awaited
            return AgentOutput(output=form_output["output"])
        except Exception as e:
            log.error(f"Error while executing form: {e}")
            return AgentOutput()
