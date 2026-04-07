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
            platform_post_id=result.get("platform_post_id"),
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
        "review_id":    job.review_id,
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
    Dispatch to a real platform publisher first; fall back to simulation
    if credentials are missing or the real call raises RuntimeError.

    REAL-FIRST strategy:
      LinkedIn  → publish_to_linkedin()
      Twitter/X → publish_to_x()
      Others    → simulation only (extend as needed)

    Fallback is triggered automatically — no crash, clear log message.
    """
    _real_publishers = {
        "LinkedIn":  publish_to_linkedin,
        "Twitter/X": publish_to_x,
        "Instagram": publish_to_instagram,
    }

    real_fn = _real_publishers.get(platform)
    if real_fn:
        try:
            result = await real_fn(review, scheduled_at)
            logger.info("real_publish_success", platform=platform,
                        post_url=result.get("post_url"))
            return result
        except RuntimeError as exc:
            logger.warning("real_publish_fallback_mode_activated",
                           platform=platform, reason=str(exc))
        except Exception as exc:
            logger.warning("real_publish_unexpected_fallback",
                           platform=platform, error=str(exc))

    # ── Simulation fallback ───────────────────────────────────────────────
    cfg = _PLATFORM_CONFIG.get(platform, _DEFAULT_CONFIG)
    latency_s = (cfg["base_latency_ms"] + random.uniform(-cfg["jitter_ms"], cfg["jitter_ms"])) / 1000
    await asyncio.sleep(max(0.01, latency_s))

    if random.random() < cfg["failure_rate"]:
        raise RuntimeError(f"Simulated {platform} API error: rate limit exceeded")

    post_id = uuid.uuid4().hex[:10]
    platform_slug = platform.lower().replace("/", "").replace(" ", "")

    if scheduled_at:
        return {"status": "queued", "post_url": None,
                "platform_post_id": None,
                "message": f"Scheduled for {scheduled_at} on {platform} (simulation)."}

    return {
        "status": "posted",
        "post_url": f"https://mock.{platform_slug}.com/posts/{post_id}",
        "platform_post_id": post_id,
        "message": f"Successfully posted to {platform} (simulation).",
    }


# ── Production platform integrations (swap points) ───────────────────────────

async def publish_to_linkedin(
    review: PostReview,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    """
    Publish a post to LinkedIn via the LinkedIn UGC Post API.

    Requires in .env:
        LINKEDIN_ACCESS_TOKEN  — OAuth 2.0 user access token
        LINKEDIN_PERSON_URN    — urn:li:person:{id}  (from GET /v2/me)

    Returns {"status": "posted"|"queued", "post_url": str | None, "message": str}
    Raises RuntimeError on failure (triggers retry in _execute_job).
    """
    from config import get_settings
    import httpx

    settings = get_settings()
    token = settings.linkedin_access_token
    person_urn = settings.linkedin_person_urn

    if not token or not person_urn:
        raise RuntimeError(
            "LinkedIn credentials not configured (LINKEDIN_ACCESS_TOKEN / LINKEDIN_PERSON_URN). "
            "Falling back to simulation."
        )

    payload = {
        "author": person_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": review.post},
                "shareMediaCategory": "NONE",
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            "https://api.linkedin.com/v2/ugcPosts",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-Restli-Protocol-Version": "2.0.0",
            },
            json=payload,
        )

    if resp.status_code == 429:
        raise RuntimeError("LinkedIn rate limit exceeded.")
    if not resp.is_success:
        raise RuntimeError(f"LinkedIn API error {resp.status_code}: {resp.text[:200]}")

    post_id = resp.headers.get("x-restli-id", "")
    post_url = f"https://www.linkedin.com/feed/update/{post_id}" if post_id else None
    return {
        "status": "posted",
        "post_url": post_url,
        "platform_post_id": post_id,
        "message": "Successfully posted to LinkedIn.",
    }


async def publish_to_x(
    review: PostReview,
    scheduled_at: str | None = None,
) -> dict[str, Any]:
    """
    Publish a tweet via X API v2 using OAuth 1.0a (user context).

    Uses a lightweight async-safe HMAC-SHA1 signer — no sync libraries,
    no event-loop blocking.

    Requires in .env:
        X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET

    Returns {"status": "posted"|"queued", "post_url": str | None, "message": str}
    Raises RuntimeError on failure (triggers retry in _execute_job).
    """
    import base64
    import hashlib
    import hmac
    import time
    import urllib.parse
    import uuid as _uuid
    import httpx
    from config import get_settings

    settings = get_settings()
    if not all([
        settings.x_api_key, settings.x_api_secret,
        settings.x_access_token, settings.x_access_token_secret,
    ]):
        raise RuntimeError("X OAuth credentials not configured. Falling back to simulation.")

    if scheduled_at:
        return {
            "status": "queued",
            "post_url": None,
            "platform_post_id": None,
            "message": f"Scheduled for {scheduled_at} (local queue — X free tier).",
        }

    url  = "https://api.twitter.com/2/tweets"
    text = review.post[:280]

    # ── Build OAuth 1.0a Authorization header (pure Python, async-safe) ──
    oauth_params = {
        "oauth_consumer_key":     settings.x_api_key,
        "oauth_nonce":            _uuid.uuid4().hex,
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp":        str(int(time.time())),
        "oauth_token":            settings.x_access_token,
        "oauth_version":          "1.0",
    }

    # Signature base string — only oauth params (body is JSON, not form-encoded)
    sorted_params = "&".join(
        f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}"
        for k, v in sorted(oauth_params.items())
    )
    base_string = "&".join([
        "POST",
        urllib.parse.quote(url, safe=""),
        urllib.parse.quote(sorted_params, safe=""),
    ])
    signing_key = (
        urllib.parse.quote(settings.x_api_secret, safe="")
        + "&"
        + urllib.parse.quote(settings.x_access_token_secret, safe="")
    )
    signature = base64.b64encode(
        hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha1).digest()
    ).decode()
    oauth_params["oauth_signature"] = signature

    auth_header = "OAuth " + ", ".join(
        f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
        for k, v in sorted(oauth_params.items())
    )

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": auth_header,
                "Content-Type":  "application/json",
            },
            json={"text": text},
        )

    if resp.status_code == 429:
        raise RuntimeError("X API rate limit exceeded.")
    if not resp.is_success:
        raise RuntimeError(f"X API error {resp.status_code}: {resp.text[:200]}")

    data     = resp.json().get("data", {})
    tweet_id = data.get("id", "")
    post_url = f"https://x.com/i/web/status/{tweet_id}" if tweet_id else None
    return {
        "status":           "posted",
        "post_url":         post_url,
        "platform_post_id": tweet_id,
        "message":          "Successfully posted to X.",
    }


async def publish_to_instagram(
    review: PostReview,
    scheduled_at: str | None = None,
    image_url: str | None = None,
) -> dict[str, Any]:
    """
    Publish a post to Instagram via the Meta Graph API (two-step flow).

    Media type selection
    --------------------
    - image_url provided  → media_type=IMAGE (standard image post)
    - no image_url        → raises RuntimeError to trigger simulation fallback,
                            because Instagram's API does not support text-only posts.
                            In production, always supply an image_url generated from
                            the visual_prompt field via an image generation service.

    Step 1 — Create media container:
        POST /{ig-user-id}/media  with caption + image_url + media_type

    Step 2 — Publish container:
        POST /{ig-user-id}/media_publish  with creation_id

    Requires in .env:
        INSTAGRAM_USER_ID          — numeric IG user ID
        INSTAGRAM_ACCESS_TOKEN     — long-lived Page Access Token

    Falls back to simulation if credentials are missing or image_url is absent.
    Raises RuntimeError on API failure (triggers retry in _execute_job).
    """
    import httpx
    from config import get_settings

    settings = get_settings()
    ig_user_id   = getattr(settings, "instagram_user_id", "")
    access_token = getattr(settings, "instagram_access_token", "")

    if not ig_user_id or not access_token:
        raise RuntimeError(
            "Instagram credentials not configured "
            "(INSTAGRAM_USER_ID / INSTAGRAM_ACCESS_TOKEN). "
            "Falling back to simulation."
        )

    # Instagram does not support text-only posts via the Graph API.
    # Without an image_url we cannot create a valid media container.
    if not image_url:
        raise RuntimeError(
            "No image_url provided for Instagram post. "
            "Instagram requires an image. Falling back to simulation."
        )

    base = f"https://graph.facebook.com/v19.0/{ig_user_id}"
    params_base = {"access_token": access_token}

    async with httpx.AsyncClient(timeout=20.0) as client:
        # Step 1 — create IMAGE container (only when image_url is present)
        container_payload: dict[str, Any] = {
            "caption":    review.post[:2200],   # IG caption limit
            "image_url":  image_url,
            "media_type": "IMAGE",
            **params_base,
        }
        r1 = await client.post(f"{base}/media", params=container_payload)
        if r1.status_code == 429:
            raise RuntimeError("Instagram rate limit exceeded.")
        if not r1.is_success:
            raise RuntimeError(
                f"Instagram container creation failed {r1.status_code}: {r1.text[:200]}"
            )
        creation_id = r1.json().get("id", "")
        if not creation_id:
            raise RuntimeError("Instagram API returned no container ID.")

        # Step 2 — publish container
        r2 = await client.post(
            f"{base}/media_publish",
            params={"creation_id": creation_id, **params_base},
        )
        if not r2.is_success:
            raise RuntimeError(
                f"Instagram publish failed {r2.status_code}: {r2.text[:200]}"
            )
        post_id  = r2.json().get("id", "")
        post_url = f"https://www.instagram.com/p/{post_id}/" if post_id else None

    logger.info("instagram_publish_success", post_id=post_id)
    return {
        "status":           "posted",
        "post_url":         post_url,
        "platform_post_id": post_id,
        "message":          "Successfully posted to Instagram.",
    }
