"""
Calendar Orchestrator
---------------------
Coordinates calendar generation and the Human-in-the-Loop feedback loop.

Responsibilities
----------------
1. generate()  — run CalendarAgent, persist result in CalendarStateStore
2. feedback()  — parse natural-language feedback, apply surgical patches,
                 return only the changed entries
3. get()       — retrieve current calendar state for a session
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from agents.calendar_agent import CalendarAgent
from orchestrator.calendar_state import CalendarSession, calendar_store
from utils.calendar_utils import parse_feedback
from utils.logger import get_logger

logger = get_logger("CalendarOrchestrator")


class CalendarOrchestrator:

    def __init__(self):
        self._agent = CalendarAgent()

    # ── Generation ────────────────────────────────────────────────────────

    async def generate(
        self,
        profile_report: dict[str, Any],
        competitor_report: dict[str, Any],
        start_date: date | str | None = None,
        days: int = 14,
    ) -> CalendarSession:
        """
        Generate a fresh 14-day calendar and store it in a new session.
        Returns the CalendarSession (contains session_id + calendar).
        """
        calendar = self._agent.generate(
            profile_report=profile_report,
            competitor_report=competitor_report,
            start_date=start_date,
            days=days,
        )
        session = calendar_store.create(calendar)
        logger.info("calendar_session_created", session_id=session.session_id, entries=len(calendar))
        return session

    # ── HITL Feedback ─────────────────────────────────────────────────────

    def feedback(
        self,
        session_id: str,
        feedback_text: str,
    ) -> dict[str, Any]:
        """
        Parse free-text feedback and apply surgical patches to the calendar.
        The session is persisted to disk after every successful change.

        Returns
        -------
        {
            "session_id": str,
            "parsed":     dict,          # what the parser understood
            "changed":    list[dict],    # only the updated entries
            "unchanged_reason": str | None
        }
        """
        session = calendar_store.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found.")

        parsed = parse_feedback(feedback_text)
        logger.info("feedback_parsed", session_id=session_id, parsed=parsed)

        target_days: list[int] = parsed["days"]

        # If no specific days mentioned, apply to ALL non-locked entries
        if not target_days:
            target_days = [e["day"] for e in session.calendar if not e.get("locked")]

        # Build patch list
        patches = []
        for day in target_days:
            idx = day - 1   # calendar is 0-indexed internally
            if 0 <= idx < len(session.calendar):
                patches.append({"day_index": idx, "patch": parsed})

        if not patches:
            return {
                "session_id": session_id,
                "parsed": parsed,
                "changed": [],
                "unchanged_reason": "No matching days found or all targeted entries are locked.",
            }

        changed = session.apply_patches(patches, feedback_text=feedback_text)
        # Persist after every mutation
        calendar_store.save_session(session)

        return {
            "session_id": session_id,
            "parsed": parsed,
            "changed": changed,
            "unchanged_reason": None if changed else "All targeted entries are locked.",
        }

    def undo(self, session_id: str) -> dict[str, Any]:
        """
        Revert the most recent feedback round for a session.
        """
        session = calendar_store.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found.")

        result = session.undo()
        if result.get("reverted"):
            calendar_store.save_session(session)
            logger.info("calendar_undo", session_id=session_id,
                        restored_days=result.get("restored_days"))
        return result

    def approve(self, session_id: str) -> dict[str, Any]:
        """
        Approve a calendar session, enabling content generation.

        Content generation is BLOCKED until this is called.
        Returns the updated session metadata.
        """
        session = calendar_store.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found.")

        session.approved    = True
        session.approved_at = datetime.utcnow().isoformat()
        calendar_store.save_session(session)
        logger.info("calendar_approved", session_id=session_id)
        return {
            "session_id":  session_id,
            "approved":    True,
            "approved_at": session.approved_at,
        }

    def is_approved(self, session_id: str) -> bool:
        """Return True if the calendar session has been approved."""
        session = calendar_store.get(session_id)
        return bool(session and session.approved)

    # ── State access ──────────────────────────────────────────────────────

    def get_calendar(self, session_id: str) -> list[dict[str, Any]]:
        session = calendar_store.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found.")
        return session.snapshot()

    def get_history(self, session_id: str) -> list[dict[str, Any]]:
        session = calendar_store.get(session_id)
        if not session:
            raise KeyError(f"Session '{session_id}' not found.")
        return session.history

    def list_sessions(self) -> list[dict[str, str]]:
        return calendar_store.list_sessions()

    def delete_session(self, session_id: str) -> bool:
        return calendar_store.delete(session_id)


# Singleton — shared across the process
calendar_orchestrator = CalendarOrchestrator()
