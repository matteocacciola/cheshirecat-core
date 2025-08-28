from typing import List
from abc import ABC, abstractmethod
from langchain_core.messages import BaseMessage
from langchain_core.documents import Document
from pydantic import Field

from cat.utils import BaseModelDict


class AgentInput(BaseModelDict):
    context: List[Document]
    tools_output: str | None = None
    input: str
    history: List[BaseMessage] = Field(default_factory=list)


class AgentOutput(BaseModelDict):
    output: str | None = None
    intermediate_steps: List = Field(default_factory=list)
    return_direct: bool = False
    with_llm_error: bool = False


class BaseAgent(ABC):
    def __init__(self, stray):
        # important so all agents have the session and utilities at disposal
        # if you subclass and override the constructor, remember to set it or call super()
        self._stray = stray

    @abstractmethod
    def execute(self, stray, *args, **kwargs) -> AgentOutput:
        """
        Execute the agents.

        Args:
            stray: StrayCat
                Stray Cat instance containing the working memory and the chat history.

        Returns:
            agent_output: AgentOutput
                Reply of the agent, instance of AgentOutput.
        """
        pass

    def __str__(self):
        return self.__class__.__name__
