"""
Publish Service
---------------
Simulates the full publish lifecycle:

  1. Jobs are created with status=queued
  2. Each job is "sent" to the platform (async simulation with realistic latency)
  3. Status transitions to posted or failed based on per-platform failure rates
  4. Every attempt is recorded in MetricsStore (latency, success/failure counts)

Simulation config (per platform)
---------------------------------
  base_latency_ms  : median round-trip time
  jitter_ms        : ± random variance added to latency
  failure_rate     : probability [0.0–1.0] of a simulated failure

Replace _simulate_platform_call() with real API calls for production.
"""
from __future__ import annotations

import asyncio
import random
import time
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PostReview, PublishJob
from db import publish_repository as pub_repo
from services.metrics import metrics
from utils.exceptions import ReviewNotApprovedError, PublishError
from utils.logger import get_logger
from utils.retry import RetryConfig, with_retry

logger = get_logger("PublishService")

# ── Per-platform simulation config ────────────────────────────────────────────

_PLATFORM_CONFIG: dict[str, dict[str, Any]] = {
    "Instagram": {"base_latency_ms": 320, "jitter_ms": 80,  "failure_rate": 0.05},
    "LinkedIn":  {"base_latency_ms": 280, "jitter_ms": 60,  "failure_rate": 0.04},
    "Twitter/X": {"base_latency_ms": 180, "jitter_ms": 50,  "failure_rate": 0.08},
    "TikTok":    {"base_latency_ms": 400, "jitter_ms": 100, "failure_rate": 0.06},
    "YouTube":   {"base_latency_ms": 500, "jitter_ms": 120, "failure_rate": 0.07},
}
_DEFAULT_CONFIG = {"base_latency_ms": 300, "jitter_ms": 75, "failure_rate": 0.05}

_REQUIRE_APPROVED = True

# Retry config for platform calls — 3 attempts, exponential back-off
_PUBLISH_RETRY = RetryConfig(max_attempts=3, base_delay=0.2, max_delay=2.0)


# ── Public API ────────────────────────────────────────────────────────────────

async def publish(
    db: AsyncSession,
    review: PostReview,
    platforms: list[str],
    scheduled_at: str | None = None,
) -> list[dict[str, Any]]:
    """
    Create queued jobs for each platform, then execute them concurrently.
    Returns a list of job result dicts.
    """
    if _REQUIRE_APPROVED and review.status != "approved":
        raise ReviewNotApprovedError(
            f"Review #{review.id} has status '{review.status}'. "
            "Only approved posts can be published."
        )

    # Create all jobs as queued first so the caller gets IDs immediately
    jobs: list[PublishJob] = []
    for platform in platforms:
        job = await pub_repo.create_job(db, review.id, platform, scheduled_at)
        jobs.append(job)
        logger.info("job_queued", job_id=job.id, review_id=review.id, platform=platform)

    await db.flush()

    # Execute all platform calls concurrently
    results = await asyncio.gather(
        *[_execute_job(db, job, review, scheduled_at) for job in jobs]
    )

    return list(results)


async def get_job_status(db: AsyncSession, job_id: int) -> dict[str, Any] | None:
    job = await pub_repo.get_job(db, job_id)
    return pub_repo.deserialise_job(job) if job else None


async def list_jobs(
    db: AsyncSession,
    review_id: int | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    jobs = await pub_repo.list_jobs(db, review_id=review_id, status=status)
    return [pub_repo.deserialise_job(j) for j in jobs]


# ── Job execution ─────────────────────────────────────────────────────────────

async def _execute_job(
    db: AsyncSession,
    job: PublishJob,
    review: PostReview,
    scheduled_at: str | None,
) -> dict[str, Any]:
    """Run one platform publish attempt, update the job row, record metrics."""
    t_start = time.perf_counter()

    try:
        result = await with_retry(
            _simulate_platform_call,
            args=(job.platform, review, scheduled_at),
            config=_PUBLISH_RETRY,
        )
        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)

        await pub_repo.update_job(
            db, job,
            status=result["status"],
            post_url=result.get("post_url"),
            latency_ms=latency_ms,
        )
        metrics.record(job.platform, result["status"], latency_ms)

        logger.info(
            "job_complete",
            job_id=job.id,
            platform=job.platform,
            status=result["status"],
            latency_ms=latency_ms,
            post_url=result.get("post_url"),
        )

    except Exception as exc:
        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
        error_msg = str(exc)

        await pub_repo.update_job(
            db, job,
            status="failed",
            error_message=error_msg,
            latency_ms=latency_ms,
        )
        metrics.record(job.platform, "failed", latency_ms)

        logger.error(
            "job_failed",
            job_id=job.id,
            platform=job.platform,
            error=error_msg,
            latency_ms=latency_ms,
        )
        result = {
            "status": "failed",
            "post_url": None,
            "message": f"Publish failed: {error_msg}",
        }

    return {
        "job_id":       job.id,
        "platform":     job.platform,
        "status":       job.status,
        "post_url":     job.post_url,
        "scheduled_at": job.scheduled_at,
        "latency_ms":   job.latency_ms,
        "message":      result.get("message", ""),
    }


# ── Platform simulation ───────────────────────────────────────────────────────

async def _simulate_platform_call(
    platform: str,
    review: PostReview,
    scheduled_at: str | None,
) -> dict[str, Any]:
    """
    Simulates a platform API call with realistic latency and random failures.

    PRODUCTION SWAP POINT
    ---------------------
    Replace this function body with real platform API calls.
    Route by platform name to the appropriate integration function:

        if platform == "LinkedIn":
            return await publish_to_linkedin(review, scheduled_at)
        elif platform == "Twitter/X":
            return await publish_to_x(review, scheduled_at)
        elif platform == "Instagram":
            return await publish_to_instagram(review, scheduled_at)
        ...

    Each integration function should return:
        {"status": "posted"|"queued", "post_url": str | None, "message": str}
    and raise RuntimeError on unrecoverable failure (triggers retry logic).
    """
    cfg = _PLATFORM_CONFIG.get(platform, _DEFAULT_CONFIG)

    # Simulate network latency
    latency_s = (cfg["base_latency_ms"] + random.uniform(-cfg["jitter_ms"], cfg["jitter_ms"])) / 1000
    await asyncio.sleep(max(0.01, latency_s))

    # Simulate random failure
    if random.random() < cfg["failure_rate"]:
        raise RuntimeError(f"Simulated {platform} API error: rate limit exceeded")

    post_id = uuid.uuid4().hex[:10]
    platform_slug = platform.lower().replace("/", "").replace(" ", "")

    if scheduled_at:
        return {
            "status": "queued",
            "post_url": None,
            "message": f"Scheduled for {scheduled_at} on {platform}.",
        }

    return {
        "status": "posted",
        "post_url": f"https://mock.{platform_slug}.com/posts/{post_id}",
        "message": f"Successfully posted to {platform}.",
    }


# ── Production platform integrations (swap points) ───────────────────────────

async def publish_to_linkedin(
    review: PostReview,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    """
    Publish a post to LinkedIn via the LinkedIn Marketing API.

    PRODUCTION IMPLEMENTATION REQUIRED
    ------------------------------------
    1. Authenticate using OAuth 2.0 (access token from settings.linkedin_access_token).
    2. Resolve the author URN: GET https://api.linkedin.com/v2/me
    3. POST to https://api.linkedin.com/v2/ugcPosts with the post payload.
    4. For scheduled posts, use the LinkedIn Scheduled Posts API.

    Docs: https://learn.microsoft.com/en-us/linkedin/marketing/integrations/community-management/shares/ugc-post-api

    Parameters
    ----------
    review       : approved PostReview ORM row (use review.post, review.hashtags)
    scheduled_at : ISO datetime string for scheduled publishing, or None for immediate

    Returns
    -------
    {"status": "posted"|"queued", "post_url": str | None, "message": str}

    Raises
    ------
    RuntimeError on API failure (triggers retry in _execute_job)
    """
    raise NotImplementedError(
        "publish_to_linkedin() is not yet implemented. "
        "See docstring for integration instructions."
    )


async def publish_to_x(
    review: PostReview,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    """
    Publish a post to X (Twitter) via the X API v2.

    PRODUCTION IMPLEMENTATION REQUIRED
    ------------------------------------
    1. Authenticate using OAuth 1.0a or OAuth 2.0 (Bearer Token for app-only,
       user context tokens for posting on behalf of a user).
    2. POST to https://api.twitter.com/2/tweets with {"text": review.post}.
    3. For scheduled posts, store locally and use a task queue (X API v2 does
       not natively support scheduled tweets via the free/basic tier).

    Docs: https://developer.x.com/en/docs/x-api/tweets/manage-tweets/api-reference/post-tweets

    Parameters
    ----------
    review       : approved PostReview ORM row
    scheduled_at : ISO datetime string, or None for immediate

    Returns
    -------
    {"status": "posted"|"queued", "post_url": str | None, "message": str}

    Raises
    ------
    RuntimeError on API failure (triggers retry in _execute_job)
    """
    raise NotImplementedError(
        "publish_to_x() is not yet implemented. "
        "See docstring for integration instructions."
    )


async def publish_to_instagram(
    review: PostReview,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    """
    Publish a post to Instagram via the Meta Graph API.

    PRODUCTION IMPLEMENTATION REQUIRED
    ------------------------------------
    1. Authenticate using a long-lived Page Access Token.
    2. Create a media container:
       POST /{ig-user-id}/media  with image_url and caption.
    3. Publish the container:
       POST /{ig-user-id}/media_publish  with creation_id.
    4. For scheduled posts, set published=false and use the scheduled_publish_time param.

    Docs: https://developers.facebook.com/docs/instagram-api/guides/content-publishing

    Parameters
    ----------
    review       : approved PostReview ORM row
    scheduled_at : ISO datetime string, or None for immediate

    Returns
    -------
    {"status": "posted"|"queued", "post_url": str | None, "message": str}

    Raises
    ------
    RuntimeError on API failure (triggers retry in _execute_job)
    """
    raise NotImplementedError(
        "publish_to_instagram() is not yet implemented. "
        "See docstring for integration instructions."
    )
