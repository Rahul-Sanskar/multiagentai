from agents.base_agent import BaseAgent
from utils.logger import get_logger
from utils.exceptions import OrchestratorError

logger = get_logger("Orchestrator")


class Orchestrator:
    """Routes tasks to the appropriate agents and aggregates results."""

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.name] = agent
        logger.info("agent_registered", agent=agent.name)

    async def dispatch(self, agent_name: str, task: str, context: dict | None = None) -> str:
        agent = self._agents.get(agent_name)
        if not agent:
            raise OrchestratorError(f"No agent registered with name '{agent_name}'")
        try:
            result = await agent.run(task, context)
            logger.info("task_completed", agent=agent_name, task=task)
            return result
        except Exception as exc:
            await agent.on_error(exc)
            raise

    async def dispatch_all(self, task: str, context: dict | None = None) -> dict[str, str]:
        results = {}
        for name, agent in self._agents.items():
            results[name] = await self.dispatch(name, task, context)
        return results
