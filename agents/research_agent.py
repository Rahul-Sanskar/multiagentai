from agents.base_agent import BaseAgent


class ResearchAgent(BaseAgent):
    """Agent responsible for gathering and summarizing information."""

    def __init__(self):
        super().__init__(name="ResearchAgent")

    async def run(self, task: str, context: dict | None = None) -> str:
        self.logger.info("running_task", task=task)
        # TODO: integrate LLM / tool calls here
        return f"[ResearchAgent] Completed: {task}"
