import json
import pytest
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate, MessagesPlaceholder

from cat import agent
from cat.experimental.form import CatFormState
from cat.looking_glass import AgentOutput
from cat.utils import default_llm_answer_prompt

from tests.utils import just_installed_plugin


@pytest.mark.asyncio
async def test_execute_agent(stray):
    # empty agent execution
    out = await agent.run_agent(
        llm=stray.large_language_model,
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

    intermediate_steps = [(("pizza_order", {}, {}), mocked_output)]

    # mock the method stray.llm
    async def mock_llm(*args, **kwargs) -> AgentOutput:
        return AgentOutput(
            output=mocked_output,
            intermediate_steps=intermediate_steps
        )
    monkeypatch.setattr("cat.agent.run_agent", mock_llm)

    async def mock_func(self, *args, **kwargs):
        self._state = CatFormState.COMPLETE
        self._model = json.loads(mocked_model)
        result = self.submit(self._model)
        self._state = CatFormState.CLOSED
        return result
    monkeypatch.setattr("cat.experimental.form.cat_form.CatForm.run", mock_func)

    # empty agent execution with form
    out = await agent.run_agent(
        llm=stray.large_language_model,
        prompt=ChatPromptTemplate.from_messages([
            HumanMessagePromptTemplate.from_template(template="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]),
        prompt_variables={"input": "I want to order a pizza"},
        tools=[p.langchainfy() for p in stray._get_procedures()]
    )
    assert isinstance(out, AgentOutput)
    assert len(out.intermediate_steps) == 1
    assert out.intermediate_steps == intermediate_steps
    assert out.output == mocked_output


@pytest.mark.asyncio
async def test_execute_main_agent_with_tool(stray, monkeypatch):
    mocked_output = "The current time is 12:00 PM."
    intermediate_steps = [(("get_the_time", {}, {}), mocked_output)]

    # mock the method stray.llm
    async def mock_llm(*args, **kwargs) -> AgentOutput:
        return AgentOutput(
            output=mocked_output,
            intermediate_steps=intermediate_steps
        )
    monkeypatch.setattr("cat.agent.run_agent", mock_llm)

    # empty agent execution with tool
    out = await agent.run_agent(
        llm=stray.large_language_model,
        prompt=ChatPromptTemplate.from_messages([
            HumanMessagePromptTemplate.from_template(template="{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ]),
        prompt_variables={"input": "What is the current time?"},
        tools=[p.langchainfy for p in stray._get_procedures()]
    )
    assert isinstance(out, AgentOutput)
    assert len(out.intermediate_steps) == 1
    assert out.intermediate_steps == intermediate_steps
