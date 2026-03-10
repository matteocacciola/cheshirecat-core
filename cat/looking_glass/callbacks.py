import json
import time
from collections.abc import Sequence
from typing import Dict, Any, List
from uuid import UUID
from langchain_core.agents import AgentAction
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.documents import Document
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult
from pydantic import BaseModel

from cat.env import get_env_bool
from cat.services.notifier import NotifierService
from cat.utils import colored_text


class ToolMessage(BaseModel):
    tool: str
    input: str
    output: str | None = None
    duration: float | None = None


class ActiveRun(BaseModel):
    name: str
    input: str
    start_time: float


class WebSocketCallbackManager(AsyncCallbackHandler):
    def __init__(self, notifier: NotifierService):
        """
        Args:
            notifier: NotifierService instance
        """
        self.notifier = notifier
        self.active_runs: Dict[str, ActiveRun] = {}

    async def on_llm_new_token(self, token: str, **kwargs) -> None:
        await self.notifier.send_chat_token(token)

    async def on_chat_model_start(self, serialized: Dict[str, Any], messages: List[List[BaseMessage]], **kwargs):
        if get_env_bool("CAT_DEBUG"):
            lc_prompt = messages[0] if isinstance(messages, list) else messages
            print(colored_text("\n============== LLM INPUT ===============", "green"))
            for m in lc_prompt:
                print(m if isinstance(m, str) else m.model_dump())
            print(colored_text("========================================", "green"))

    async def on_llm_end(self, response: LLMResult, **kwargs):
        """Log LLM final response."""
        if get_env_bool("CAT_DEBUG"):
            print(colored_text("\n============== LLM OUTPUT ===============", "blue"))
            print(response)
            print(colored_text("========================================", "blue"))

    async def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        **kwargs: Any,
    ) -> None:
        tool_name = serialized.get("name", "Unknown Tool")
        self.active_runs[str(run_id)] = ActiveRun(name=tool_name, input=input_str, start_time=time.perf_counter())

        notification = ToolMessage(tool=tool_name, input=input_str)
        await self.notifier.send_tool_message(notification.model_dump_json())

    async def on_tool_end(self, output: str, *, run_id: UUID, **kwargs: Any) -> None:
        run_data = self.active_runs.pop(str(run_id), None)
        if run_data:
            tool_name = run_data.name
            duration = time.perf_counter() - run_data["start_time"]

            notification = ToolMessage(tool=tool_name, input=run_data.input, output=output, duration=duration)
            await self.notifier.send_tool_message(notification.model_dump_json())

    async def on_tool_error(self, error: Exception, **kwargs: Any) -> None:
        await self.notifier.send_error(error)

    async def on_chain_error(self, error: Exception, **kwargs: Any) -> None:
        await self.notifier.send_error(error)

    async def on_agent_action(self, action: AgentAction, **kwargs):
        await self.notifier.send_thought_message(action.log)

    async def on_retriever_end(self, documents: Sequence[Document], *, run_id: UUID, **kwargs):
        await self.notifier.send_context(json.dumps([doc.page_content for doc in documents]))
