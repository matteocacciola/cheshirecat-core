import json

import pytest

from cat.experimental.form import CatFormState
from cat.factory.agent import AgentOutput, CatAgent, LLMAction
from cat.utils import default_llm_answer_prompt

from tests.utils import just_installed_plugin


@pytest.mark.asyncio
async def test_execute_main_agent(stray):
    main_agent = CatAgent(stray)

    # empty agent execution
    out = await main_agent.execute()
    assert isinstance(out, AgentOutput)
    assert out.intermediate_steps == []
    assert out.output == default_llm_answer_prompt()


@pytest.mark.asyncio
async def test_execute_main_agent_with_form_submit(secure_client, secure_client_headers, stray, monkeypatch):
    just_installed_plugin(secure_client, secure_client_headers)
    stray.working_memory.user_message.text = "I want to order a pizza"

    mocked_model = "{\"pizza_type\": \"Margherita\", \"pizza_border\": \"high\", \"phone\": \"1234567890\"}"
    mocked_output = f"Form submitted: {mocked_model}".replace('"', "'")

    # mock the method stray.llm
    async def mock_llm(*args, **kwargs) -> LLMAction:
        return LLMAction(
            output="",
            tools=[{"name": "pizza_order", "args": {}}]
        )
    monkeypatch.setattr(stray, "llm", mock_llm)

    async def mock_next(self, *args, **kwargs):
        self._state = CatFormState.COMPLETE
        self._model = json.loads(mocked_model)
        result = self._submit(self._model)
        self._state = CatFormState.CLOSED
        return result
    monkeypatch.setattr("cat.experimental.form.cat_form.CatForm.next", mock_next)

    main_agent = CatAgent(stray)

    # empty agent execution with form
    out = await main_agent.execute()
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
    stray.working_memory.user_message.text = "What is the current time?"

    # mock the method stray.llm
    async def mock_llm(*args, **kwargs) -> LLMAction:
        return LLMAction(
            output="",
            tools=[{"name": "get_the_time", "args": {}}]
        )
    monkeypatch.setattr(stray, "llm", mock_llm)

    main_agent = CatAgent(stray)

    # empty agent execution with tool
    out = await main_agent.execute()
    assert isinstance(out, AgentOutput)
    assert out.intermediate_steps[0][0] == ('get_the_time', {})
    assert out.intermediate_steps[0][1].startswith("The current time is")
    assert out.output.startswith("The current time is")
