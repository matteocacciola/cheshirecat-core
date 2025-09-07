import json
import pytest
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate

from cat.experimental.form import CatFormState
from cat.looking_glass.dormouse import AgentOutput, LLMAction
from cat.utils import default_llm_answer_prompt

from tests.utils import just_installed_plugin


@pytest.mark.asyncio
async def test_execute_agent(stray):
    # empty agent execution
    out = await stray.agent.run(
        prompt=ChatPromptTemplate.from_messages([
            HumanMessagePromptTemplate.from_template(template="hey")
        ]),
    )
    assert isinstance(out, AgentOutput)
    assert out.intermediate_steps == []
    assert out.output == default_llm_answer_prompt()


@pytest.mark.asyncio
async def test_execute_agent_with_form_submit(secure_client, secure_client_headers, stray, monkeypatch):
    just_installed_plugin(secure_client, secure_client_headers)

    mocked_model = "{\"pizza_type\": \"Margherita\", \"pizza_border\": \"high\", \"phone\": \"1234567890\"}"
    mocked_output = f"Form submitted: {mocked_model}".replace('"', "'")

    # mock the method stray.llm
    async def mock_llm(*args, **kwargs) -> LLMAction:
        return LLMAction(
            output=mocked_output,
            tools=[{"name": "pizza_order", "args": {}}]
        )
    monkeypatch.setattr(stray.agent, "_langchain_run", mock_llm)

    async def mock_next(self, *args, **kwargs):
        self._state = CatFormState.COMPLETE
        self._model = json.loads(mocked_model)
        result = self.submit(self._model)
        self._state = CatFormState.CLOSED
        return result
    monkeypatch.setattr("cat.experimental.form.cat_form.CatForm.next", mock_next)

    # empty agent execution with form
    out = await stray.agent.run(
        prompt=ChatPromptTemplate.from_messages([
            HumanMessagePromptTemplate.from_template(template="{input}")
        ]),
        prompt_variables={"input": "I want to order a pizza"},
        procedures=stray._get_procedures()
    )
    assert isinstance(out, AgentOutput)
    assert out.intermediate_steps == [
        (
            ('pizza_order', {}),
            mocked_output
        )
    ]
    assert out.output == mocked_output


@pytest.mark.asyncio
async def test_execute_main_agent_with_tool(stray, monkeypatch):
    mocked_output = "The current time is 12:00 PM."

    # mock the method stray.llm
    async def mock_llm(*args, **kwargs) -> LLMAction:
        return LLMAction(
            output=mocked_output,
            tools=[{"name": "get_the_time", "args": {}}]
        )
    monkeypatch.setattr(stray.agent, "_langchain_run", mock_llm)

    # empty agent execution with tool
    out = await stray.agent.run(
        prompt=ChatPromptTemplate.from_messages([
            HumanMessagePromptTemplate.from_template(template="{input}")
        ]),
        prompt_variables={"input": "What is the current time?"},
        procedures=stray._get_procedures()
    )
    assert isinstance(out, AgentOutput)
    assert out.intermediate_steps[0][0] == ('get_the_time', {})
    assert out.intermediate_steps[0][1].startswith("The current time is")
    assert out.output.startswith("The current time is")
