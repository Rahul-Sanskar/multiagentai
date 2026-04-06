"""
Calendar Agent
--------------
Generates a 14-day content calendar from profile + competitor reports.
Each entry: day, date, platform, format, time, topic, source, priority, locked.
"""
from __future__ import annotations

import itertools
from datetime import date
from typing import Any

from agents.base_agent import BaseAgent
from utils.calendar_utils import build_topic_pool, generate_slots


class CalendarAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="CalendarAgent")

    # ── Agent protocol ────────────────────────────────────────────────────

    async def run(self, task: str, context: dict | None = None) -> str:
        import json
        ctx = context or {}
        calendar = self.generate(
            profile_report=ctx.get("profile_report", {}),
            competitor_report=ctx.get("competitor_report", {}),
            start_date=ctx.get("start_date"),
            days=ctx.get("days", 14),
        )
        return json.dumps(calendar, indent=2, default=str)

    # ── Core generation (sync, reusable) ─────────────────────────────────

    def generate(
        self,
        profile_report: dict[str, Any],
        competitor_report: dict[str, Any],
        start_date: date | str | None = None,
        days: int = 14,
    ) -> list[dict[str, Any]]:
        """
        Build a `days`-entry content calendar.

        Parameters
        ----------
        profile_report    : output of ProfileIntelligenceAgent.analyze()
        competitor_report : output of CompetitorAnalysisAgent.analyze()
        start_date        : ISO date string or date object (defaults to today)
        days              : number of calendar entries to generate
        """
        if isinstance(start_date, str):
            from datetime import datetime
            start_date = datetime.fromisoformat(start_date).date()
        start_date = start_date or date.today()

        self.logger.info("generating_calendar", days=days, start=str(start_date))

        topic_pool = build_topic_pool(profile_report, competitor_report)
        slots = generate_slots(start_date, days, profile_report)

        # Assign topics — cycle through pool if fewer topics than days
        topic_cycle = itertools.cycle(topic_pool) if topic_pool else itertools.cycle(
            [{"topic": "general content", "source": "fallback", "priority": "low"}]
        )

        for slot in slots:
            t = next(topic_cycle)
            slot["topic"] = t["topic"]
            slot["source"] = t["source"]
            slot["priority"] = t["priority"]

        self.logger.info("calendar_generated", entries=len(slots))
        return slots
