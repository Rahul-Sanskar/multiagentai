from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from db.models import AgentRun


async def create_run(db: AsyncSession, agent_name: str, task: str) -> AgentRun:
    run = AgentRun(agent_name=agent_name, task=task, status="running")
    db.add(run)
    await db.flush()
    return run


async def complete_run(db: AsyncSession, run_id: int, result: str) -> AgentRun | None:
    run = await db.get(AgentRun, run_id)
    if run:
        run.result = result
        run.status = "completed"
    return run


async def fail_run(db: AsyncSession, run_id: int, error: str) -> AgentRun | None:
    run = await db.get(AgentRun, run_id)
    if run:
        run.result = error
        run.status = "failed"
    return run


async def list_runs(db: AsyncSession) -> list[AgentRun]:
    result = await db.execute(select(AgentRun).order_by(AgentRun.created_at.desc()))
    return list(result.scalars().all())
