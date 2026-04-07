"""
Pipeline Orchestrator
---------------------
Chains every stage of the content pipeline in order:

  1. Profile Analysis      (ProfileIntelligenceAgent)
  2. Competitor Analysis   (CompetitorAnalysisAgent)
  3. RAG Ingestion         (RAGPipeline)
  4. RAG-enriched context  (retrieve_context → ContentContext.keywords)
  5. Calendar Generation   (CalendarOrchestrator)
  6. Content Creation      (ContentCreationOrchestrator, one post per calendar entry)
  7. Review Creation       (ReviewService — all posts stored as pending)
  8. Auto-approve          (optional, controlled by auto_approve flag)
  9. Publish               (PublishService — only approved reviews)

Each stage receives the output of the previous one.
The full run result is a PipelineResult dataclass.

Usage
-----
    from orchestrator.pipeline_orchestrator import PipelineOrchestrator

    orch = PipelineOrchestrator()
    result = await orch.run(
        my_posts=MY_POSTS,
        competitor_posts=COMPETITOR_POSTS,
        db=db_session,
        days=14,
        platforms=["Instagram", "LinkedIn"],
        auto_approve=True,
    )
    print(result.summary())
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agents.competitor_analysis_agent import CompetitorAnalysisAgent
from agents.content_context import ContentContext
from agents.profile_intelligence_agent import ProfileIntelligenceAgent
from orchestrator.calendar_orchestrator import CalendarOrchestrator
from orchestrator.content_creation_orchestrator import ContentCreationOrchestrator
from services import review_service
from services.publish_service import publish as publish_jobs
from services.rag_pipeline import RAGPipeline
from utils.logger import get_logger

logger = get_logger("PipelineOrchestrator")

# How many RAG results to pull per calendar entry to enrich keywords
_RAG_TOP_K = 5
# Max calendar entries to generate content + reviews for in one run
_MAX_CONTENT_ENTRIES = 14
# Paths for persisted RAG index
_RAG_INDEX_PATH  = Path("data/rag.index")
_RAG_CHUNKS_PATH = Path("data/rag_chunks.json")


@dataclass
class StageResult:
    stage: str
    success: bool
    data: Any = None
    error: str | None = None


@dataclass
class PipelineResult:
    profile_report: dict[str, Any] = field(default_factory=dict)
    competitor_report: dict[str, Any] = field(default_factory=dict)
    rag_stats: dict[str, Any] = field(default_factory=dict)
    calendar_session_id: str = ""
    calendar: list[dict[str, Any]] = field(default_factory=list)
    reviews: list[dict[str, Any]] = field(default_factory=list)
    publish_results: list[dict[str, Any]] = field(default_factory=list)
    stages: list[StageResult] = field(default_factory=list)

    def summary(self) -> str:
        lines = ["── Pipeline Run Summary ──────────────────────────"]
        for s in self.stages:
            icon = "✓" if s.success else "✗"
            detail = f"  error={s.error}" if s.error else ""
            lines.append(f"  {icon} {s.stage}{detail}")
        lines.append(f"  calendar entries : {len(self.calendar)}")
        lines.append(f"  reviews created  : {len(self.reviews)}")
        posted = sum(1 for r in self.publish_results if r.get("status") == "posted")
        failed = sum(1 for r in self.publish_results if r.get("status") == "failed")
        lines.append(f"  publish jobs     : {posted} posted / {failed} failed")
        return "\n".join(lines)


class PipelineOrchestrator:
    """
    Runs the full content pipeline end-to-end.
    All agents and services are singletons — safe to reuse across calls.
    """

    def __init__(self):
        self._profile    = ProfileIntelligenceAgent()
        self._competitor = CompetitorAnalysisAgent()
        self._calendar   = CalendarOrchestrator()
        self._creator    = ContentCreationOrchestrator()
        # RAG is per-run so indexes don't bleed between calls
        self._rag: RAGPipeline | None = None

    # ── Main entry point ──────────────────────────────────────────────────

    async def run(
        self,
        my_posts: list[dict[str, Any]],
        competitor_posts: list[dict[str, Any]],
        db: AsyncSession,
        *,
        start_date: date | str | None = None,
        days: int = 14,
        platforms: list[str] | None = None,
        auto_approve: bool = False,
        rag_query: str = "trending topics and high engagement content",
    ) -> PipelineResult:
        """
        Run all pipeline stages in sequence.

        Parameters
        ----------
        my_posts          : list of own social media post dicts
        competitor_posts  : list of competitor post dicts
        db                : async SQLAlchemy session (caller manages commit)
        start_date        : calendar start date (defaults to today)
        days              : number of calendar entries (max 14)
        platforms         : platforms to publish to (defaults to ["Instagram"])
        auto_approve      : if True, auto-approve all reviews before publishing
        rag_query         : query used to enrich ContentContext keywords from RAG
        """
        platforms = platforms or ["Instagram"]
        days = min(days, _MAX_CONTENT_ENTRIES)
        result = PipelineResult()

        # ── Stage 1: Profile Analysis ─────────────────────────────────────
        try:
            profile_report = self._profile.analyze(my_posts)
            result.profile_report = profile_report
            result.stages.append(StageResult("profile_analysis", True))
            logger.info("stage_complete", stage="profile_analysis")
        except Exception as exc:
            result.stages.append(StageResult("profile_analysis", False, error=str(exc)))
            logger.error("stage_failed", stage="profile_analysis", error=str(exc))
            return result

        # ── Stage 2: Competitor Analysis ──────────────────────────────────
        try:
            competitor_report = self._competitor.analyze(profile_report, competitor_posts)
            result.competitor_report = competitor_report
            result.stages.append(StageResult("competitor_analysis", True))
            logger.info("stage_complete", stage="competitor_analysis")
        except Exception as exc:
            result.stages.append(StageResult("competitor_analysis", False, error=str(exc)))
            logger.error("stage_failed", stage="competitor_analysis", error=str(exc))
            return result

        # ── Stage 3: RAG Ingestion ────────────────────────────────────────
        try:
            self._rag = RAGPipeline()
            # Load persisted index if available to avoid rebuilding every run
            if _RAG_INDEX_PATH.exists() and _RAG_CHUNKS_PATH.exists():
                self._rag.load(_RAG_INDEX_PATH, _RAG_CHUNKS_PATH)
                logger.info("rag_index_loaded_from_disk",
                            chunks=self._rag.chunk_count)
            n_profile    = self._rag.ingest(profile_report,    source="profile_report")
            n_competitor = self._rag.ingest(competitor_report, source="competitor_report")
            # Persist updated index so the next run can reuse it
            try:
                self._rag.save(_RAG_INDEX_PATH, _RAG_CHUNKS_PATH)
                logger.info("rag_index_saved", path=str(_RAG_INDEX_PATH))
            except Exception as save_exc:
                logger.warning("rag_index_save_failed", error=str(save_exc))
            result.rag_stats = self._rag.stats()
            result.stages.append(StageResult("rag_ingestion", True,
                                             data={"profile_chunks": n_profile,
                                                   "competitor_chunks": n_competitor}))
            logger.info("stage_complete", stage="rag_ingestion",
                        chunks=n_profile + n_competitor)
        except Exception as exc:
            result.stages.append(StageResult("rag_ingestion", False, error=str(exc)))
            logger.warning("stage_failed", stage="rag_ingestion", error=str(exc))
            # RAG failure is non-fatal — continue without enrichment

        # ── Stage 4: Calendar Generation ─────────────────────────────────
        try:
            session = await self._calendar.generate(
                profile_report=profile_report,
                competitor_report=competitor_report,
                start_date=start_date,
                days=days,
            )
            result.calendar_session_id = session.session_id
            result.calendar = session.calendar
            result.stages.append(StageResult("calendar_generation", True,
                                             data={"session_id": session.session_id}))
            logger.info("stage_complete", stage="calendar_generation",
                        entries=len(session.calendar))
        except Exception as exc:
            result.stages.append(StageResult("calendar_generation", False, error=str(exc)))
            logger.error("stage_failed", stage="calendar_generation", error=str(exc))
            return result

        # ── Stage 5 + 6: Content Creation + Review (per calendar entry) ──
        # Approval gate: content generation requires calendar approval.
        # In auto_approve mode the pipeline self-approves the calendar.
        if auto_approve:
            self._calendar.approve(result.calendar_session_id)
            logger.info("stage_complete", stage="calendar_auto_approved",
                        session_id=result.calendar_session_id)
        elif not self._calendar.is_approved(result.calendar_session_id):
            result.stages.append(StageResult(
                "content_and_review", False,
                error="Calendar not approved. Call POST /api/v1/calendar/{id}/approve first.",
            ))
            logger.warning("content_blocked_calendar_not_approved",
                           session_id=result.calendar_session_id)
            return result
        tone = profile_report.get("writing_style", {}).get("tone", "informational")
        profile_keywords = profile_report.get("topics", {}).get("top_keywords", [])

        review_tasks = [
            self._create_review_for_entry(
                entry=entry,
                db=db,
                tone=tone,
                profile_keywords=profile_keywords,
                rag_query=rag_query,
            )
            for entry in result.calendar
        ]

        review_results = await asyncio.gather(*review_tasks, return_exceptions=True)

        reviews: list[dict[str, Any]] = []
        errors: list[str] = []
        for r in review_results:
            if isinstance(r, Exception):
                errors.append(str(r))
            elif r is not None:
                reviews.append(r)

        result.reviews = reviews
        result.stages.append(StageResult(
            "content_and_review",
            success=len(errors) == 0,
            data={"created": len(reviews), "errors": len(errors)},
            error="; ".join(errors) if errors else None,
        ))
        logger.info("stage_complete", stage="content_and_review",
                    created=len(reviews), errors=len(errors))

        if not reviews:
            return result

        # ── Stage 7: Auto-approve (optional) ─────────────────────────────
        if auto_approve:
            try:
                approve_tasks = [
                    review_service.set_status(db, r["id"], "approved",
                                              note="auto-approved by pipeline")
                    for r in reviews
                ]
                await asyncio.gather(*approve_tasks)
                await db.flush()
                result.stages.append(StageResult("auto_approve", True,
                                                  data={"approved": len(reviews)}))
                logger.info("stage_complete", stage="auto_approve", count=len(reviews))
            except Exception as exc:
                result.stages.append(StageResult("auto_approve", False, error=str(exc)))
                logger.error("stage_failed", stage="auto_approve", error=str(exc))
                return result

        # ── Stage 8: Publish ──────────────────────────────────────────────
        if auto_approve:
            try:
                from db.review_repository import get as get_review_row
                publish_tasks = []
                for r in reviews:
                    review_row = await get_review_row(db, r["id"])
                    if review_row and review_row.status == "approved":
                        publish_tasks.append(
                            publish_jobs(db, review_row, platforms)
                        )

                all_publish = await asyncio.gather(*publish_tasks, return_exceptions=True)
                flat_results: list[dict[str, Any]] = []
                pub_errors: list[str] = []
                for batch in all_publish:
                    if isinstance(batch, Exception):
                        pub_errors.append(str(batch))
                    else:
                        flat_results.extend(batch)

                await db.flush()
                result.publish_results = flat_results
                posted = sum(1 for r in flat_results if r.get("status") == "posted")
                failed = sum(1 for r in flat_results if r.get("status") == "failed")
                result.stages.append(StageResult(
                    "publish",
                    success=len(pub_errors) == 0,
                    data={"posted": posted, "failed": failed},
                    error="; ".join(pub_errors) if pub_errors else None,
                ))
                logger.info("stage_complete", stage="publish",
                            posted=posted, failed=failed)

                # ── Stage 9: Schedule impact tracking ────────────────────
                # Persist a ScheduledImpact row for every successful publish
                # job so metrics are fetched after the configured delay even
                # if the server restarts before the delay expires.
                try:
                    from services.impact_tracker import schedule_impact_fetch
                    from config import get_settings as _get_settings

                    delay = _get_settings().impact_fetch_delay_seconds
                    eng   = profile_report.get("engagement", {})
                    expected_baseline = {
                        "likes":    float(eng.get("avg_likes", 0)),
                        "comments": float(eng.get("avg_comments", 0)),
                        "shares":   float(eng.get("avg_shares", 0)),
                    }
                    # Build a review_id lookup from the reviews list
                    review_by_id = {r["id"]: r for r in reviews}

                    scheduled = 0
                    for job_result in flat_results:
                        if job_result.get("status") != "posted":
                            continue
                        job_id    = job_result.get("job_id")
                        review_id = job_result.get("review_id")
                        platform  = job_result.get("platform", "")
                        topic     = review_by_id.get(review_id, {}).get("topic", "")

                        if not job_id or not review_id:
                            continue

                        await schedule_impact_fetch(
                            db=db,
                            job_id=job_id,
                            review_id=review_id,
                            platform=platform,
                            topic=topic,
                            expected=expected_baseline,
                            delay_seconds=delay,
                        )
                        scheduled += 1

                    if scheduled:
                        logger.info("stage_complete", stage="impact_scheduled",
                                    count=scheduled, delay_seconds=delay)
                except Exception as exc:
                    # Impact scheduling is non-fatal — never block the pipeline
                    logger.warning("impact_schedule_failed", error=str(exc))
            except Exception as exc:
                result.stages.append(StageResult("publish", False, error=str(exc)))
                logger.error("stage_failed", stage="publish", error=str(exc))
        else:
            result.stages.append(StageResult(
                "publish", True,
                data={"skipped": True,
                      "reason": "auto_approve=False; approve reviews manually then call /publish"}
            ))

        return result

    # ── Per-entry helper ──────────────────────────────────────────────────

    async def _create_review_for_entry(
        self,
        entry: dict[str, Any],
        db: AsyncSession,
        tone: str,
        profile_keywords: list[str],
        rag_query: str,
    ) -> dict[str, Any] | None:
        """
        Build a ContentContext for one calendar entry, optionally enriching
        keywords from RAG, then create a review.
        """
        # RAG enrichment: pull relevant keywords AND full chunk texts for this entry's topic
        rag_keywords: list[str] = []
        rag_chunks: list[str] = []
        if self._rag and self._rag.chunk_count > 0:
            query = f"{rag_query} {entry.get('topic', '')}"
            chunks = self._rag.retrieve_context(query, top_k=_RAG_TOP_K)
            for chunk in chunks:
                # Collect chunk text for grounding the LLM prompt
                rag_chunks.append(chunk.text[:200])
                # Also extract keyword tokens for keyword enrichment
                words = [w.strip(".,;:") for w in chunk.text.split()
                         if len(w) > 3 and w.isalpha()]
                rag_keywords.extend(words[:3])

        # Merge: profile keywords + RAG-retrieved keywords, deduplicated
        merged_keywords = list(dict.fromkeys(profile_keywords[:5] + rag_keywords[:5]))

        ctx = ContentContext(
            topic=entry.get("topic") or "general content",
            tone=tone,
            platform=_normalise_platform(entry.get("platform", "Instagram")),
            keywords=merged_keywords,
            rag_chunks=rag_chunks,   # passed through to CopyAgent for grounded generation
        )

        return await review_service.create_review(db, ctx)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise_platform(platform: str) -> str:
    """Ensure platform string matches ContentContext's expected values."""
    _map = {
        "twitter": "Twitter/X",
        "twitter/x": "Twitter/X",
        "x": "Twitter/X",
        "instagram": "Instagram",
        "linkedin": "LinkedIn",
        "tiktok": "TikTok",
        "youtube": "YouTube",
    }
    return _map.get(platform.lower(), platform)


# Singleton
pipeline_orchestrator = PipelineOrchestrator()
