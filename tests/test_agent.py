import json

from cat import AgenticWorkflowTask, AgenticWorkflowOutput, RecallSettings
from cat.looking_glass.mad_hatter.decorators.experimental.form import CatFormState
from cat.utils import default_llm_answer_prompt

from tests.utils import just_installed_plugin


async def test_execute_agent(stray):
    agent_input = AgenticWorkflowTask(
        user_prompt="hey",
    )

    # empty agent execution
    af = await stray.agentic_workflow()
    out = await af.run(
        task=agent_input,
        llm=await stray.large_language_model(),
    )
    assert isinstance(out, AgenticWorkflowOutput)
    assert out.intermediate_steps == []
    assert out.output == default_llm_answer_prompt()


async def test_execute_agent_with_form_submit(secure_client, secure_client_headers, stray, monkeypatch):
    await just_installed_plugin(secure_client, secure_client_headers)

    mocked_model = "{\"pizza_type\": \"Margherita\", \"pizza_border\": \"high\", \"phone\": \"1234567890\"}"
    mocked_output = f"Form submitted: {mocked_model}".replace('"', "'")

    intermediate_steps = [(("pizza_order", {}, {}), mocked_output)]

    # mock the method running the LLM
    async def mock_llm(*args, **kwargs) -> AgenticWorkflowOutput:
        return AgenticWorkflowOutput(
            output=mocked_output,
            intermediate_steps=intermediate_steps
        )
    monkeypatch.setattr("cat.looking_glass.mad_hatter.decorators.experimental.form.CatForm._run_agent", mock_llm)
    monkeypatch.setattr("cat.services.factory.agentic_workflow.CoreAgenticWorkflow.run", mock_llm)

    async def mock_func(self, *args, **kwargs):
        self._state = CatFormState.COMPLETE
        self._model = json.loads(mocked_model)
        result = await self.submit(self._model)
        self._state = CatFormState.CLOSED
        return result
    monkeypatch.setattr("cat.looking_glass.mad_hatter.decorators.experimental.form.CatForm.next", mock_func)

    message = "I want to order a pizza"

    # empty agent execution with form
    embedder = await stray.embedder()
    tools = await stray.get_procedures(RecallSettings(embedding=embedder.embed_query(message)))
    agent_input = AgenticWorkflowTask(
        user_prompt=message,
        tools=tools,
    )
    af = await stray.agentic_workflow()
    out = await af.run(
        task=agent_input,
        llm=await stray.large_language_model(),
    )
    assert isinstance(out, AgenticWorkflowOutput)
    assert len(out.intermediate_steps) == 1
    assert out.intermediate_steps == intermediate_steps
    assert out.output == mocked_output


async def test_execute_main_agent_with_tool(stray, monkeypatch):
    mocked_output = "The current time is 12:00 PM."
    intermediate_steps = [(("get_the_time", {}, {}), mocked_output)]

    # mock the method running the LLM
    async def mock_llm(*args, **kwargs) -> AgenticWorkflowOutput:
        return AgenticWorkflowOutput(
            output=mocked_output,
            intermediate_steps=intermediate_steps
        )
    monkeypatch.setattr("cat.looking_glass.mad_hatter.decorators.experimental.form.CatForm._run_agent", mock_llm)
    monkeypatch.setattr("cat.services.factory.agentic_workflow.CoreAgenticWorkflow.run", mock_llm)

    message = "What is the current time?"

    # empty agent execution with tool
    embedder = await stray.embedder()
    tools = await stray.get_procedures(RecallSettings(embedding=embedder.embed_query(message)))
    agent_input = AgenticWorkflowTask(
        user_prompt=message,
        tools=tools,
    )
    af = await stray.agentic_workflow()
    out = await af.run(
        task=agent_input,
        llm=await stray.large_language_model(),
    )
    assert isinstance(out, AgenticWorkflowOutput)
    assert len(out.intermediate_steps) == 1
    assert out.intermediate_steps == intermediate_steps


async def test_execute_main_agent_with_mcp_client_tool(stray, secure_client, secure_client_headers, monkeypatch):
    await just_installed_plugin(secure_client, secure_client_headers)

    result = "Processed test with param2=42"
    details = {"param3": None, "param4": None, "param5": None, "param6": None}
    mocked_output = f"MockResponse(result={result}, code=200, details={details})"

    intermediate_steps = [(("mock_mcp_client", {}, {}), mocked_output)]

    # mock the method running the LLM
    async def mock_llm(*args, **kwargs) -> AgenticWorkflowOutput:
        return AgenticWorkflowOutput(
            output=mocked_output,
            intermediate_steps=intermediate_steps
        )
    monkeypatch.setattr("cat.looking_glass.mad_hatter.decorators.experimental.form.CatForm._run_agent", mock_llm)
    monkeypatch.setattr("cat.services.factory.agentic_workflow.CoreAgenticWorkflow.run", mock_llm)

    message = "Call mock_procedure with param1='test', param2=42"

    # empty agent execution with tool
    embedder = await stray.embedder()
    tools = await stray.get_procedures(RecallSettings(embedding=embedder.embed_query(message)))
    agent_input = AgenticWorkflowTask(
        user_prompt=message,
        tools=tools,
    )
    af = await stray.agentic_workflow()
    out = await af.run(
        task=agent_input,
        llm=await stray.large_language_model(),
    )
    assert isinstance(out, AgenticWorkflowOutput)
    assert len(out.intermediate_steps) == 1
    assert out.intermediate_steps[0][1] == mocked_output
