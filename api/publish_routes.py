"""
Publish & Metrics routes
------------------------
GET  /api/v1/publish/jobs                   list all jobs
GET  /api/v1/publish/jobs/{job_id}          poll a single job
GET  /api/v1/publish/metrics                current metrics snapshot
POST /api/v1/publish/metrics/reset          reset metrics (dev/test only)
POST /api/v1/publish/impact/{job_id}        fetch + store post-publish metrics now
GET  /api/v1/publish/performance            analyze performance across review IDs
GET  /api/v1/publish/suggestions            adaptive calendar suggestions
"""
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from db.session import get_db
from services import publish_service
from services.metrics import metrics
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/publish", tags=["publish"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class JobOut(BaseModel):
    id: int
    review_id: int
    platform: str
    status: str                  # queued | posted | failed
    post_url: str | None
    scheduled_at: str | None
    error_message: str | None
    latency_ms: float | None
    created_at: str | None
    updated_at: str | None


class LatencyStats(BaseModel):
    count: int
    min: float
    max: float
    avg: float
    p50: float
    p95: float
    p99: float


class PlatformMetrics(BaseModel):
    attempts: int
    success: int
    failed: int
    queued: int
    success_rate: float
    failure_rate: float
    latency_ms: LatencyStats


class GlobalMetrics(BaseModel):
    attempts: int
    success: int
    failed: int
    queued: int
    success_rate: float
    failure_rate: float
    avg_latency_ms: float


class MetricsSnapshot(BaseModel):
    uptime_seconds: float
    global_: GlobalMetrics
    by_platform: dict[str, PlatformMetrics]

    class Config:
        populate_by_name = True


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/jobs", response_model=list[JobOut])
async def list_jobs(
    review_id: int | None = Query(default=None),
    status: str | None = Query(default=None, description="queued | posted | failed"),
    db: AsyncSession = Depends(get_db),
):
    return await publish_service.list_jobs(db, review_id=review_id, status=status)


@router.get("/jobs/{job_id}", response_model=JobOut)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await publish_service.get_job_status(db, job_id)
    if not job:
        raise HTTPException(404, f"Job {job_id} not found.")
    return job


@router.get("/metrics")
async def get_metrics() -> dict[str, Any]:
    snap = metrics.snapshot()
    # rename "global" key to avoid Python keyword clash in response
    snap["global_"] = snap.pop("global")
    return snap


@router.post("/metrics/reset", status_code=204)
async def reset_metrics():
    metrics.reset()


# ── Impact tracker endpoints ──────────────────────────────────────────────────

@router.post("/impact/{job_id}")
async def fetch_impact(
    job_id: int,
    topic: str = Query(default=""),
    expected_likes: float = Query(default=0.0),
    expected_comments: float = Query(default=0.0),
    expected_shares: float = Query(default=0.0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """
    Fetch post-publish engagement metrics for a specific publish job right now.
    Normally called automatically after a delay; use this for manual/testing.
    """
    from services.impact_tracker import fetch_and_store
    from db.models import PublishJob

    job = await db.get(PublishJob, job_id)
    if not job:
        raise HTTPException(404, f"PublishJob {job_id} not found.")

    impact = await fetch_and_store(
        db=db,
        job_id=job_id,
        review_id=job.review_id,
        platform=job.platform,
        topic=topic,
        expected={"likes": expected_likes, "comments": expected_comments, "shares": expected_shares},
    )
    import json
    return {
        "id":              impact.id,
        "job_id":          job_id,
        "platform":        impact.platform,
        "topic":           impact.topic,
        "likes":           impact.likes,
        "comments":        impact.comments,
        "shares":          impact.shares,
        "impressions":     impact.impressions,
        "performance_tag": impact.performance_tag,
        "insight":         json.loads(impact.insight_json or "{}"),
    }


@router.get("/performance")
async def get_performance(
    review_ids: str = Query(description="Comma-separated review IDs, e.g. 1,2,3"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Aggregate performance analysis across a set of published reviews."""
    from services.impact_tracker import analyze_performance
    ids = [int(x.strip()) for x in review_ids.split(",") if x.strip().isdigit()]
    return await analyze_performance(db, ids)


@router.get("/suggestions")
async def get_suggestions(
    review_ids: str = Query(description="Comma-separated review IDs"),
    remaining_topics: str = Query(default="", description="Comma-separated remaining calendar topics"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Return adaptive calendar suggestions based on post-publish performance."""
    from services.impact_tracker import adaptive_suggestions
    ids = [int(x.strip()) for x in review_ids.split(",") if x.strip().isdigit()]
    calendar = [{"topic": t.strip(), "day": i + 1}
                for i, t in enumerate(remaining_topics.split(",")) if t.strip()]
    return await adaptive_suggestions(db, ids, calendar)
