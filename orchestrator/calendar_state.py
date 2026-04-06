"""
Calendar session state — with JSON file persistence and undo support.

CalendarSession  : mutable state for one session, including full feedback history
                   and undo stack for reverting the last change.
CalendarStateStore : registry of sessions, persisted to data/calendar_sessions.json
                     so sessions survive process restarts.
"""
from __future__ import annotations

import json
import uuid
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

_SESSIONS_PATH = Path("data/calendar_sessions.json")


class CalendarSession:
    """
    Holds the mutable state for one calendar generation session.

    Supports:
    - apply_patches()  — apply feedback and record in history
    - undo()           — revert the most recent feedback round
    """

    def __init__(self, session_id: str, calendar: list[dict[str, Any]]):
        self.session_id = session_id
        self.calendar: list[dict[str, Any]] = calendar
        self.history: list[dict[str, Any]] = []   # audit trail of every patch round
        self._undo_stack: list[list[dict[str, Any]]] = []  # snapshots for undo
        self.created_at: str = datetime.utcnow().isoformat()
        self.updated_at: str = self.created_at

    # ── Mutation ──────────────────────────────────────────────────────────

    def apply_patches(
        self,
        patches: list[dict[str, Any]],
        feedback_text: str = "",
    ) -> list[dict[str, Any]]:
        """
        Apply a list of entry patches, push a snapshot onto the undo stack,
        and record the change in history.

        Returns only the entries that were actually changed.
        """
        from utils.calendar_utils import apply_patch

        # Save snapshot before mutating so undo() can restore it
        self._undo_stack.append(deepcopy(self.calendar))

        changed: list[dict[str, Any]] = []
        for p in patches:
            idx = p["day_index"]
            if 0 <= idx < len(self.calendar):
                old = self.calendar[idx]
                new = apply_patch(old, p["patch"])
                if new != old:
                    self.calendar[idx] = new
                    changed.append(new)

        if changed:
            self.history.append({
                "timestamp":    datetime.utcnow().isoformat(),
                "feedback":     feedback_text,
                "changed_days": [e["day"] for e in changed],
            })
            self.updated_at = datetime.utcnow().isoformat()
        else:
            # Nothing changed — pop the snapshot we just pushed
            self._undo_stack.pop()

        return changed

    def undo(self) -> dict[str, Any]:
        """
        Revert the most recent feedback round.

        Returns
        -------
        {"reverted": True, "restored_days": [...]}  on success
        {"reverted": False, "reason": "..."}         if nothing to undo
        """
        if not self._undo_stack:
            return {"reverted": False, "reason": "No changes to undo."}

        previous = self._undo_stack.pop()
        reverted_days = [
            e["day"] for e, p in zip(self.calendar, previous) if e != p
        ]
        self.calendar = previous

        if self.history:
            undone = self.history.pop()
            self.history.append({
                "timestamp":    datetime.utcnow().isoformat(),
                "feedback":     f"[UNDO] reverted: {undone.get('feedback', '')}",
                "changed_days": reverted_days,
            })
        self.updated_at = datetime.utcnow().isoformat()
        return {"reverted": True, "restored_days": reverted_days}

    # ── Read ──────────────────────────────────────────────────────────────

    def get_entry(self, day: int) -> dict[str, Any] | None:
        """Retrieve a single entry by 1-based day number."""
        for entry in self.calendar:
            if entry["day"] == day:
                return entry
        return None

    def snapshot(self) -> list[dict[str, Any]]:
        """Return a deep copy of the current calendar."""
        return deepcopy(self.calendar)

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Serialise to a JSON-safe dict (undo stack is not persisted)."""
        return {
            "session_id": self.session_id,
            "calendar":   self.calendar,
            "history":    self.history,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CalendarSession":
        """Restore a CalendarSession from a serialised dict."""
        session = cls(d["session_id"], d["calendar"])
        session.history    = d.get("history", [])
        session.created_at = d.get("created_at", datetime.utcnow().isoformat())
        session.updated_at = d.get("updated_at", session.created_at)
        return session


class CalendarStateStore:
    """
    Registry of CalendarSession objects with JSON file persistence.

    Sessions are loaded from _SESSIONS_PATH on startup and saved after
    every mutation so they survive process restarts.
    """

    def __init__(self, path: Path = _SESSIONS_PATH):
        self._sessions: dict[str, CalendarSession] = {}
        self._path = path
        self._load()

    # ── CRUD ──────────────────────────────────────────────────────────────

    def create(self, calendar: list[dict[str, Any]]) -> CalendarSession:
        """Create a new session, persist it, and return it."""
        sid = str(uuid.uuid4())
        session = CalendarSession(sid, deepcopy(calendar))
        self._sessions[sid] = session
        self._save()
        return session

    def get(self, session_id: str) -> CalendarSession | None:
        return self._sessions.get(session_id)

    def delete(self, session_id: str) -> bool:
        removed = bool(self._sessions.pop(session_id, None))
        if removed:
            self._save()
        return removed

    def save_session(self, session: CalendarSession) -> None:
        """Persist a session after an in-place mutation (feedback, undo)."""
        self._sessions[session.session_id] = session
        self._save()

    def list_sessions(self) -> list[dict[str, str]]:
        return [
            {
                "session_id": s.session_id,
                "created_at": s.created_at,
                "updated_at": s.updated_at,
            }
            for s in self._sessions.values()
        ]

    # ── Persistence ───────────────────────────────────────────────────────

    def _save(self) -> None:
        """
        Write all sessions to disk as JSON.
        Errors are silently swallowed — a persistence failure must never
        break the calendar API.
        """
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            payload = {sid: s.to_dict() for sid, s in self._sessions.items()}
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _load(self) -> None:
        """
        Load sessions from disk on startup.
        Missing or corrupt files are silently ignored.
        """
        if not self._path or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            for sid, data in raw.items():
                self._sessions[sid] = CalendarSession.from_dict(data)
        except Exception:
            pass


# Singleton store shared across the process
calendar_store = CalendarStateStore()
