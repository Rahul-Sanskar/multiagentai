"""
Publish & Metrics routes
------------------------
GET  /api/v1/publish/jobs                   list all jobs (filter by status/review)
GET  /api/v1/publish/jobs/{job_id}          poll a single job
GET  /api/v1/publish/metrics                current metrics snapshot
POST /api/v1/publish/metrics/reset          reset metrics (dev/test only)
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
