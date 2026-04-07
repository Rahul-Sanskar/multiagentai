"""
PublishJob repository — all DB access for publish jobs.
"""
from __future__ import annotations

from typing import Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PublishJob


async def create_job(
    db: AsyncSession,
    review_id: int,
    platform: str,
    scheduled_at: str | None = None,
) -> PublishJob:
    job = PublishJob(
        review_id=review_id,
        platform=platform,
        status="queued",
        scheduled_at=scheduled_at,
    )
    db.add(job)
    await db.flush()
    return job


async def get_job(db: AsyncSession, job_id: int) -> PublishJob | None:
    return await db.get(PublishJob, job_id)


async def list_jobs(
    db: AsyncSession,
    review_id: int | None = None,
    status: str | None = None,
) -> list[PublishJob]:
    q = select(PublishJob).order_by(PublishJob.created_at.desc())
    if review_id is not None:
        q = q.where(PublishJob.review_id == review_id)
    if status:
        q = q.where(PublishJob.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


async def update_job(
    db: AsyncSession,
    job: PublishJob,
    status: str,
    post_url: str | None = None,
    platform_post_id: str | None = None,
    error_message: str | None = None,
    latency_ms: float | None = None,
) -> PublishJob:
    job.status = status
    if post_url is not None:
        job.post_url = post_url
    if platform_post_id is not None:
        job.platform_post_id = platform_post_id
    if error_message is not None:
        job.error_message = error_message
    if latency_ms is not None:
        job.latency_ms = latency_ms
    return job


def deserialise_job(job: PublishJob) -> dict[str, Any]:
    return {
        "id":            job.id,
        "review_id":     job.review_id,
        "platform":      job.platform,
        "status":        job.status,
        "post_url":      job.post_url,
        "scheduled_at":  job.scheduled_at,
        "error_message": job.error_message,
        "latency_ms":    job.latency_ms,
        "created_at":    job.created_at.isoformat() if job.created_at else None,
        "updated_at":    job.updated_at.isoformat() if job.updated_at else None,
    }
