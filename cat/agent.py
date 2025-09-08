import re
from typing import List, Dict, Any, Tuple
from langchain.agents import create_tool_calling_agent, AgentExecutor
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import ChatPromptTemplate, HumanMessagePromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import StructuredTool


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
        llm : BaseLanguageModel
            The language model to use for generating responses.
        prompt : ChatPromptTemplate
            The prompt template to use for the LLM.
        prompt_variables : Dict[str, Any], optional
            Variables to fill in the prompt template, by default None.
        tools : List[StructuredTool], optional
            List of tools available to the agent, by default None.
        callbacks : List[BaseCallbackHandler], optional
            List of callback handlers for logging and monitoring, by default None.

    Returns:
        AgentOutput
            The final output from the agent, including text and any actions taken.
    """
    from cat.looking_glass import AgentOutput, LoggingCallbackHandler

    def clean_response(response: str) -> str:
        # parse the `response` string and get the text from <answer></answer> tag
        if "<answer>" in response and "</answer>" in response:
            start = response.index("<answer>") + len("<answer>")
            end = response.index("</answer>")
            return response[start:end].strip()
        # otherwise, remove from `response` all the text between whichever tag and then return the remaining string
        # This pattern matches any complete tag pair: <tagname>content</tagname>
        cleaned = re.sub(r'<([^>]+)>.*?</\1>', '', response, flags=re.DOTALL)
        return cleaned.strip()

    def extract_info(action) -> Tuple[Tuple[str | None, Dict, Dict] | None, str]:
        if not isinstance(action, tuple) or len(action) < 2:
            return None, str(action)
        # Extract the main fields from the first element of the tuple
        tool = getattr(action[0], "tool")
        tool_input = getattr(action[0], "tool_input", {})
        usage_metadata = getattr(action[0], "usage_metadata", {})
        response = action[1]
        # Create a tuple with the extracted information
        return (tool, tool_input, usage_metadata), response

    async def run_no_bind():
        chain = prompt | llm
        langchain_msg = await chain.ainvoke(prompt_variables, config=RunnableConfig(callbacks=callbacks))
        return AgentOutput(output=getattr(langchain_msg, "content", str(langchain_msg)))

    async def run_with_bind():
        # Check if the prompt already has the required placeholders
        prompt.messages.append(HumanMessagePromptTemplate.from_template("{agent_scratchpad}"))
        # Create the agent with proper prompt structure
        agent = create_tool_calling_agent(
            llm=llm,
            tools=tools,
            prompt=ChatPromptTemplate.from_messages(prompt.messages),
        )
        # Create the agent executor
        agent_executor = AgentExecutor.from_agent_and_tools(
            agent=agent,
            tools=tools,
            return_intermediate_steps=True,
            verbose=True,
            handle_parsing_errors=True,  # Add error handling
        )
        # Run the agent
        result = await agent_executor.ainvoke(prompt_variables, config=RunnableConfig(callbacks=callbacks))
        result["output"] = clean_response(result.get("output", "")).strip()
        result["intermediate_steps"] = [extract_info(step) for step in result.get("intermediate_steps", [])]
        return AgentOutput(**result)

    callbacks = callbacks or []
    callbacks.append(LoggingCallbackHandler())

    # Intrinsic detection of tool binding support
    can_bind_tools = tools and hasattr(llm, "bind_tools")

    prompt_variables = prompt_variables or {}

    # Direct LLM invocation
    if not can_bind_tools:
        res = await run_no_bind()
        return res

    try:
        res = await run_with_bind()
        return res
    except Exception:
        res = await run_no_bind()
        return res
