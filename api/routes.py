from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from api.schemas import TaskRequest, TaskResponse, AgentRunOut
from db.session import get_db
from orchestrator.registry import get_orchestrator
from services import agent_run_service
from utils.exceptions import OrchestratorError

router = APIRouter(prefix="/api/v1", tags=["agents"])


@router.post("/run", response_model=TaskResponse)
async def run_agent(payload: TaskRequest, db: AsyncSession = Depends(get_db)):
    orch = get_orchestrator()
    run = await agent_run_service.create_run(db, payload.agent_name, payload.task)
    try:
        result = await orch.dispatch(payload.agent_name, payload.task, payload.context)
        await agent_run_service.complete_run(db, run.id, result)
        return TaskResponse(agent_name=payload.agent_name, task=payload.task, result=result)
    except OrchestratorError as exc:
        await agent_run_service.fail_run(db, run.id, str(exc))
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        await agent_run_service.fail_run(db, run.id, str(exc))
        raise HTTPException(status_code=500, detail="Agent execution failed")


@router.get("/runs", response_model=list[AgentRunOut])
async def list_runs(db: AsyncSession = Depends(get_db)):
    return await agent_run_service.list_runs(db)


@router.get("/agents")
async def list_agents():
    orch = get_orchestrator()
    return {"agents": list(orch._agents.keys())}
