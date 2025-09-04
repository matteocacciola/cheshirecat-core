import pytest

from cheshirecat.agents.main_agent import DefaultAgent
from cheshirecat.agents.base_agent import AgentOutput
from cheshirecat.utils import default_llm_answer_prompt


def test_main_agent_instantiation(stray):
    main_agent = DefaultAgent(stray)
    assert main_agent.verbose in [True, False]


@pytest.mark.asyncio
async def test_execute_main_agent(stray):
    main_agent = DefaultAgent(stray)

    # empty agent execution
    out = await main_agent.execute()
    assert isinstance(out, AgentOutput)
    assert out.intermediate_steps == []
    assert out.output == default_llm_answer_prompt()
