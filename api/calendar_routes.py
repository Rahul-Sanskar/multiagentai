"""
Calendar API routes
-------------------
POST /api/v1/calendar/generate          — generate a new 14-day calendar
POST /api/v1/calendar/{id}/feedback     — apply HITL feedback
GET  /api/v1/calendar/{id}              — get current calendar state
GET  /api/v1/calendar/{id}/history      — get feedback audit trail
GET  /api/v1/calendar/sessions          — list active sessions
DELETE /api/v1/calendar/{id}            — delete a session
"""
from typing import Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from orchestrator.calendar_orchestrator import calendar_orchestrator

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


# ── Request / Response schemas ────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    profile_report: dict[str, Any]
    competitor_report: dict[str, Any]
    start_date: str | None = None       # ISO date, e.g. "2024-02-01"
    days: int = Field(default=14, ge=1, le=30)


class FeedbackRequest(BaseModel):
    feedback: str = Field(..., min_length=3)


class CalendarEntry(BaseModel):
    day: int
    date: str
    platform: str
    format: str
    time: str
    topic: str | None
    source: str | None
    priority: str | None
    locked: bool


class GenerateResponse(BaseModel):
    session_id: str
    calendar: list[CalendarEntry]


class FeedbackResponse(BaseModel):
    session_id: str
    parsed: dict[str, Any]
    changed: list[CalendarEntry]
    unchanged_reason: str | None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/generate", response_model=GenerateResponse)
async def generate_calendar(body: GenerateRequest):
    session = await calendar_orchestrator.generate(
        profile_report=body.profile_report,
        competitor_report=body.competitor_report,
        start_date=body.start_date,
        days=body.days,
    )
    return GenerateResponse(session_id=session.session_id, calendar=session.calendar)


@router.post("/{session_id}/feedback", response_model=FeedbackResponse)
async def apply_feedback(session_id: str, body: FeedbackRequest):
    try:
        result = calendar_orchestrator.feedback(session_id, body.feedback)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return FeedbackResponse(**result)


@router.post("/{session_id}/undo")
async def undo_feedback(session_id: str):
    """Revert the most recent feedback round for this session."""
    try:
        return calendar_orchestrator.undo(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/approve")
async def approve_calendar(session_id: str):
    """
    Approve a calendar session.
    Content generation is blocked until this endpoint is called.
    """
    try:
        return calendar_orchestrator.approve(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/sessions")
async def list_sessions():
    return calendar_orchestrator.list_sessions()


@router.get("/{session_id}", response_model=list[CalendarEntry])
async def get_calendar(session_id: str):
    try:
        return calendar_orchestrator.get_calendar(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{session_id}/history")
async def get_history(session_id: str):
    try:
        return calendar_orchestrator.get_history(session_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    if not calendar_orchestrator.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found.")
    return {"deleted": session_id}
