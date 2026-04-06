from pydantic import BaseModel
from datetime import datetime


class TaskRequest(BaseModel):
    agent_name: str
    task: str
    context: dict | None = None


class TaskResponse(BaseModel):
    agent_name: str
    task: str
    result: str


class AgentRunOut(BaseModel):
    id: int
    agent_name: str
    task: str
    result: str | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
