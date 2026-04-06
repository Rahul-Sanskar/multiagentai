from abc import ABC, abstractmethod
from utils.logger import get_logger


class BaseAgent(ABC):
    """All agents must inherit from this class."""

    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(name)

    @abstractmethod
    async def run(self, task: str, context: dict | None = None) -> str:
        """Execute the agent's task and return a result string."""

    async def on_error(self, error: Exception) -> None:
        self.logger.error("agent_error", agent=self.name, error=str(error))
