"""
Impact Tracker Service
----------------------
Fetches post-publish engagement metrics from platforms after a configurable
delay. Uses DB-backed scheduling (ScheduledImpact table) so pending fetches
survive server restarts.

Public API
----------
    schedule_impact_fetch(db, ...)
        — persist a ScheduledImpact row; spawn a background task to execute it

    recover_pending_fetches(db_factory)
        — called on startup: re-queue any pending rows whose fetch_after has passed

    fetch_and_store(db, job_id, ...)
        — fetch metrics now and persist a PostImpact row

    analyze_performance(db, review_ids)
    adaptive_suggestions(db, review_ids, calendar)
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PostImpact, PublishJob, ScheduledImpact
from utils.logger import get_logger

logger = get_logger("ImpactTracker")

_HIGH_THRESHOLD = 1.3
_LOW_THRESHOLD  = 0.7


# ── DB-backed scheduling ──────────────────────────────────────────────────────

async def schedule_impact_fetch(
    db: AsyncSession,
    job_id: int,
    review_id: int,
    platform: str,
    topic: str,
    expected: dict[str, float],
    delay_seconds: int = 3600,
) -> ScheduledImpact:
    """
    Persist a ScheduledImpact row and spawn a background task to execute it.

    The DB row ensures the fetch survives a server restart — on next startup
    `recover_pending_fetches()` will re-queue any rows that are still pending.
    """
    fetch_after = datetime.now(timezone.utc) + timedelta(seconds=delay_seconds)
    row = ScheduledImpact(
        publish_job_id=job_id,
        review_id=review_id,
        platform=platform,
        topic=topic,
        expected_json=json.dumps(expected),
        fetch_after=fetch_after,
        status="pending",
    )
    db.add(row)
    await db.flush()

    logger.info("impact_scheduled", scheduled_id=row.id,
                job_id=job_id, fetch_after=fetch_after.isoformat())

    # Spawn background task — will wait until fetch_after, then execute
    asyncio.create_task(_run_scheduled(row.id, delay_seconds))
    return row


async def _run_scheduled(scheduled_id: int, delay_seconds: int) -> None:
    """
    Background task: wait, then execute the fetch and update the DB row.
    Uses its own session so it's independent of the request lifecycle.
    """
    from db.session import AsyncSessionLocal

    await asyncio.sleep(delay_seconds)

    async with AsyncSessionLocal() as db:
        try:
            row = await db.get(ScheduledImpact, scheduled_id)
            if not row or row.status != "pending":
                return  # already processed or cancelled

            # Mark as running
            row.status = "running"
            await db.flush()

            expected = json.loads(row.expected_json or "{}")
            await _fetch_and_store(
                db=db,
                job_id=row.publish_job_id,
                review_id=row.review_id,
                platform=row.platform,
                topic=row.topic,
                expected=expected,
            )
            row.status = "done"
            await db.commit()
            logger.info("impact_fetch_complete",
                        scheduled_id=scheduled_id, job_id=row.publish_job_id)

        except Exception as exc:
            try:
                row = await db.get(ScheduledImpact, scheduled_id)
                if row:
                    row.status = "failed"
                    row.error = str(exc)[:500]
                    await db.commit()
            except Exception:
                pass
            logger.error("impact_fetch_failed",
                         scheduled_id=scheduled_id, error=str(exc))


async def recover_pending_fetches(db_factory) -> int:
    """
    Called on server startup. Finds all ScheduledImpact rows with
    status='pending' whose fetch_after time has already passed and
    re-queues them as background tasks.

    Returns the number of rows recovered.
    """
    now = datetime.now(timezone.utc)
    recovered = 0

    async with db_factory() as db:
        result = await db.execute(
            select(ScheduledImpact).where(ScheduledImpact.status == "pending")
        )
        rows: list[ScheduledImpact] = list(result.scalars().all())

    for row in rows:
        # Make fetch_after timezone-aware if stored as naive UTC
        fa = row.fetch_after
        if fa.tzinfo is None:
            fa = fa.replace(tzinfo=timezone.utc)

        remaining = max(0, (fa - now).total_seconds())
        asyncio.create_task(_run_scheduled(row.id, int(remaining)))
        recovered += 1
        logger.info("impact_recovered", scheduled_id=row.id,
                    job_id=row.publish_job_id, delay_remaining_s=int(remaining))

    if recovered:
        logger.info("impact_recovery_complete", count=recovered)
    return recovered


# ── Core fetch + store ────────────────────────────────────────────────────────

async def fetch_and_store(
    db: AsyncSession,
    job_id: int,
    review_id: int,
    platform: str,
    topic: str,
    expected: dict[str, float],
) -> PostImpact:
    """Public wrapper — fetch metrics now and persist a PostImpact row."""
    return await _fetch_and_store(db, job_id, review_id, platform, topic, expected)


async def _fetch_and_store(
    db: AsyncSession,
    job_id: int,
    review_id: int,
    platform: str,
    topic: str,
    expected: dict[str, float],
) -> PostImpact:
    job = await db.get(PublishJob, job_id)
    platform_post_id = job.platform_post_id if job else None

    raw_metrics = await _fetch_platform_metrics(platform, platform_post_id)
    tag     = _tag_performance(raw_metrics, expected)
    insight = _build_insight(raw_metrics, expected, topic, tag)

    impact = PostImpact(
        publish_job_id=job_id,
        review_id=review_id,
        platform=platform,
        topic=topic,
        impressions=raw_metrics.get("impressions", 0),
        likes=raw_metrics.get("likes", 0),
        comments=raw_metrics.get("comments", 0),
        shares=raw_metrics.get("shares", 0),
        clicks=raw_metrics.get("clicks", 0),
        expected_likes=expected.get("likes", 0.0),
        expected_comments=expected.get("comments", 0.0),
        expected_shares=expected.get("shares", 0.0),
        performance_tag=tag,
        insight_json=json.dumps(insight),
        fetched_at=datetime.now(timezone.utc),
    )
    db.add(impact)
    await db.flush()
    logger.info("impact_stored", job_id=job_id, tag=tag,
                likes=impact.likes, expected_likes=impact.expected_likes)
    return impact


# ── Platform metric fetchers ──────────────────────────────────────────────────

async def _fetch_platform_metrics(
    platform: str,
    platform_post_id: str | None,
) -> dict[str, int]:
    """
    Fetch engagement metrics from the platform API.
    Falls back to zeros if credentials are missing or the post ID is unknown.
    """
    if not platform_post_id:
        logger.warning("impact_no_post_id", platform=platform)
        return {}

    try:
        if platform == "Twitter/X":
            return await _fetch_x_metrics(platform_post_id)
        if platform == "LinkedIn":
            return await _fetch_linkedin_metrics(platform_post_id)
    except Exception as exc:
        logger.warning("impact_metric_fetch_failed",
                       platform=platform, error=str(exc))
    return {}


async def _fetch_x_metrics(tweet_id: str) -> dict[str, int]:
    """
    Fetch tweet metrics via X API v2 public_metrics.
    Requires X_BEARER_TOKEN in .env.
    """
    from config import get_settings
    import httpx

    settings = get_settings()
    if not settings.x_bearer_token:
        raise RuntimeError("X_BEARER_TOKEN not configured.")

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://api.twitter.com/2/tweets/{tweet_id}",
            headers={"Authorization": f"Bearer {settings.x_bearer_token}"},
            params={"tweet.fields": "public_metrics"},
        )

    if not resp.is_success:
        raise RuntimeError(f"X metrics fetch failed: {resp.status_code}")

    m = resp.json().get("data", {}).get("public_metrics", {})
    return {
        "likes":       m.get("like_count", 0),
        "comments":    m.get("reply_count", 0),
        "shares":      m.get("retweet_count", 0),
        "impressions": m.get("impression_count", 0),
    }


async def _fetch_linkedin_metrics(post_id: str) -> dict[str, int]:
    """
    Fetch LinkedIn post metrics via the Social Actions API.
    Requires LINKEDIN_ACCESS_TOKEN in .env.
    """
    from config import get_settings
    import httpx

    settings = get_settings()
    if not settings.linkedin_access_token:
        raise RuntimeError("LINKEDIN_ACCESS_TOKEN not configured.")

    encoded_id = post_id.replace(":", "%3A")
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"https://api.linkedin.com/v2/socialActions/{encoded_id}",
            headers={
                "Authorization": f"Bearer {settings.linkedin_access_token}",
                "X-Restli-Protocol-Version": "2.0.0",
            },
        )

    if not resp.is_success:
        raise RuntimeError(f"LinkedIn metrics fetch failed: {resp.status_code}")

    data = resp.json()
    return {
        "likes":    data.get("likesSummary", {}).get("totalLikes", 0),
        "comments": data.get("commentsSummary", {}).get("totalFirstLevelComments", 0),
        "shares":   data.get("shareStatistics", {}).get("shareCount", 0),
    }


# ── Performance analysis ──────────────────────────────────────────────────────

def _tag_performance(
    actual: dict[str, int],
    expected: dict[str, float],
) -> str:
    """
    Compare actual vs expected engagement and return a performance tag.

    Returns "high" | "average" | "low" | "unknown"
    """
    exp_total = (expected.get("likes", 0) +
                 expected.get("comments", 0) +
                 expected.get("shares", 0))
    if exp_total == 0:
        return "unknown"

    act_total = (actual.get("likes", 0) +
                 actual.get("comments", 0) +
                 actual.get("shares", 0))

    ratio = act_total / exp_total
    if ratio >= _HIGH_THRESHOLD:
        return "high"
    if ratio <= _LOW_THRESHOLD:
        return "low"
    return "average"


def _build_insight(
    actual: dict[str, int],
    expected: dict[str, float],
    topic: str,
    tag: str,
) -> dict[str, Any]:
    """Build a structured insight dict for storage and API response."""
    act_total = actual.get("likes", 0) + actual.get("comments", 0) + actual.get("shares", 0)
    exp_total = (expected.get("likes", 0) + expected.get("comments", 0) + expected.get("shares", 0))
    delta_pct = round((act_total - exp_total) / max(exp_total, 1) * 100, 1)

    messages = {
        "high":    f"'{topic}' outperformed expectations by {delta_pct}%. Consider adding similar topics.",
        "low":     f"'{topic}' underperformed by {abs(delta_pct)}%. Consider replacing with higher-engagement topics.",
        "average": f"'{topic}' performed as expected.",
        "unknown": f"Insufficient baseline data for '{topic}'.",
    }
    return {
        "topic":       topic,
        "tag":         tag,
        "delta_pct":   delta_pct,
        "actual":      actual,
        "expected":    expected,
        "insight":     messages.get(tag, ""),
    }


# ── Performance analysis across a session ────────────────────────────────────

async def analyze_performance(
    db: AsyncSession,
    review_ids: list[int],
) -> dict[str, Any]:
    """
    Aggregate PostImpact rows for a set of reviews and return a
    performance summary with high/low topic lists.

    Returns
    -------
    {
        "total_posts": int,
        "high_performing": [{"topic": str, "delta_pct": float}],
        "underperforming": [{"topic": str, "delta_pct": float}],
        "avg_delta_pct": float,
    }
    """
    if not review_ids:
        return {"total_posts": 0, "high_performing": [], "underperforming": [], "avg_delta_pct": 0.0}

    result = await db.execute(
        select(PostImpact).where(PostImpact.review_id.in_(review_ids))
    )
    impacts: list[PostImpact] = list(result.scalars().all())

    if not impacts:
        return {"total_posts": 0, "high_performing": [], "underperforming": [], "avg_delta_pct": 0.0}

    high, low, deltas = [], [], []
    for imp in impacts:
        insight = json.loads(imp.insight_json or "{}")
        delta = insight.get("delta_pct", 0.0)
        deltas.append(delta)
        entry = {"topic": imp.topic, "delta_pct": delta, "platform": imp.platform}
        if imp.performance_tag == "high":
            high.append(entry)
        elif imp.performance_tag == "low":
            low.append(entry)

    return {
        "total_posts":      len(impacts),
        "high_performing":  sorted(high, key=lambda x: x["delta_pct"], reverse=True),
        "underperforming":  sorted(low,  key=lambda x: x["delta_pct"]),
        "avg_delta_pct":    round(sum(deltas) / len(deltas), 1) if deltas else 0.0,
    }


# ── Adaptive re-planner ───────────────────────────────────────────────────────

async def adaptive_suggestions(
    db: AsyncSession,
    review_ids: list[int],
    remaining_calendar: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Analyse performance data and suggest changes to the remaining calendar.

    Returns
    -------
    {
        "insight": str,
        "recommended_changes": [
            {"day": int, "current_topic": str, "suggested_topic": str, "reason": str}
        ]
    }
    """
    perf = await analyze_performance(db, review_ids)
    high_topics = [e["topic"] for e in perf["high_performing"]]
    low_topics  = {e["topic"] for e in perf["underperforming"]}

    changes: list[dict[str, Any]] = []
    for entry in remaining_calendar:
        topic = entry.get("topic", "")
        if topic in low_topics and high_topics:
            # Suggest replacing with the best-performing topic
            suggestion = high_topics[0]
            changes.append({
                "day":             entry.get("day"),
                "current_topic":   topic,
                "suggested_topic": suggestion,
                "reason":          f"'{topic}' underperformed. '{suggestion}' has high engagement.",
            })

    if not changes and high_topics:
        insight = (
            f"Top performing topic: '{high_topics[0]}'. "
            "Consider adding more content on this theme."
        )
    elif changes:
        insight = (
            f"{len(changes)} calendar entries suggested for replacement "
            f"based on post-publish performance data."
        )
    else:
        insight = "Insufficient performance data for recommendations yet."

    return {"insight": insight, "recommended_changes": changes}
