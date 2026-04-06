from agents.base_agent import BaseAgent


class ExecutorAgent(BaseAgent):
    """Agent responsible for executing actions based on a plan."""

    def __init__(self):
        super().__init__(name="ExecutorAgent")

    async def run(self, task: str, context: dict | None = None) -> str:
        self.logger.info("running_task", task=task)
        # TODO: integrate tool execution logic here
        return f"[ExecutorAgent] Completed: {task}"
