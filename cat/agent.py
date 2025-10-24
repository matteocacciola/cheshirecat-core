import re
from typing import List, Dict, Any, Tuple
from langchain_classic.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool

from cat.log import log


def _clean_response(response: str) -> str:
    # parse the `response` string and get the text from <answer></answer> tag
    if "<answer>" in response and "</answer>" in response:
        start = response.index("<answer>") + len("<answer>")
        end = response.index("</answer>")
        return response[start:end].strip()

    # otherwise, remove from `response` all the text between whichever tag and then return the remaining string
    # This pattern matches any complete tag pair: <tagname>content</tagname>
    cleaned = re.sub(r'<([^>]+)>.*?</\1>', '', response, flags=re.DOTALL)
    return cleaned.strip()


def _extract_info(action) -> Tuple[Tuple[str | None, Dict, Dict] | None, str]:
    if not isinstance(action, tuple) or len(action) < 2:
        return None, str(action)

    # Extract the main fields from the first element of the tuple
    tool = getattr(action[0], "tool")
    tool_input = getattr(action[0], "tool_input", {})
    usage_metadata = getattr(action[0], "usage_metadata", {})

    # Create a tuple with the extracted information
    return (tool, tool_input, usage_metadata), action[1]


async def _run_no_bind(
    llm: BaseLanguageModel,
    prompt: ChatPromptTemplate,
    prompt_variables: Dict[str, Any] = None,
    callbacks: List[BaseCallbackHandler] = None,
) -> "AgentOutput":
    from cat.looking_glass import AgentOutput

    prompt_variables = prompt_variables or {}

    chain = prompt | llm
    langchain_msg = await chain.ainvoke(prompt_variables, config=RunnableConfig(callbacks=callbacks))

    output = getattr(langchain_msg, "content", str(langchain_msg))
    return AgentOutput(output=_clean_response(output))


async def _run_with_bind(
    llm: BaseLanguageModel,
    prompt: ChatPromptTemplate,
    prompt_variables: Dict[str, Any] = None,
    tools: List[StructuredTool] = None,
    callbacks: List[BaseCallbackHandler] = None,
) -> "AgentOutput":
    from cat.looking_glass import AgentOutput

    prompt.messages.append(HumanMessagePromptTemplate.from_template("{agent_scratchpad}"))

    # Create the agent with proper prompt structure
    agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)
    # Create the agent executor
    agent_executor = AgentExecutor.from_agent_and_tools(
        agent=agent,
        tools=tools,
        callbacks=callbacks,
        return_intermediate_steps=True,
        verbose=True,
        handle_parsing_errors=True,  # Add error handling
    )
    # Run the agent
    langchain_msg = await agent_executor.ainvoke(
        prompt_variables or {}, config=RunnableConfig(callbacks=callbacks)
    )

    cleaned_output = _clean_response(langchain_msg.get("output", "")).strip()
    extracted_steps = [_extract_info(step) for step in langchain_msg.get("intermediate_steps", [])]
    return AgentOutput(output=cleaned_output, intermediate_steps=extracted_steps)


async def run_agent(
    llm: BaseLanguageModel,
    prompt: ChatPromptTemplate,
    prompt_variables: Dict[str, Any] = None,
    tools: List[StructuredTool] = None,
    callbacks: List[BaseCallbackHandler] = None,
) -> "AgentOutput":
    """
    Executes the Dormouse agent with the given prompt and procedures. It processes the LLM output, handles tool
    calls, and generates the final response. It also cleans the response from any tags.

    Args:
        llm (BaseLanguageModel): The language model to use for generating responses.
        prompt (ChatPromptTemplate): The prompt template to use for the LLM.
        prompt_variables (Dict[str, Any], optional): Variables to fill in the prompt template, by default None.
        tools (List[StructuredTool], optional): List of tools available to the agent, by default None.
        callbacks (List[BaseCallbackHandler], optional):  List of callback handlers for logging and monitoring, by default None.

    Returns:
        AgentOutput
            The final output from the agent, including text and any actions taken.
    """
    from cat.looking_glass import LoggingCallbackHandler

    callbacks = callbacks or []
    callbacks.append(LoggingCallbackHandler())

    # Intrinsic detection of tool binding support
    can_bind_tools = tools and hasattr(llm, "bind_tools")

    # Direct LLM invocation
    if not can_bind_tools:
        res = await _run_no_bind(llm, prompt, prompt_variables, callbacks)
        return res

    try:
        res = await _run_with_bind(llm, prompt, prompt_variables, tools, callbacks)
        return res
    except Exception as e:
        log.warning(f"Tool binding failed with error: {e}. Falling back to direct LLM invocation.")

        res = await _run_no_bind(llm, prompt, prompt_variables, callbacks)
        return res
