"""
X (Twitter) API Client — free tier, read-only
----------------------------------------------
Uses the v2 search/recent endpoint with Bearer Token auth.
Free tier limits: 1 request / 15 min per app, 10 results max per call.

Public interface
----------------
    fetch_user_posts(username, max_results)  -> list[dict]   # top-level, toggle-aware
    fetch_search_posts(query, max_results)   -> list[dict]

Toggle
------
    USE_REAL_API = True   — hit the live X v2 API
    USE_REAL_API = False  — return mock data immediately (no network call)

Both functions:
  - Return normalised post dicts compatible with ProfileIntelligenceAgent
  - Fall back to mock data on any API / network failure (never crash)
  - Raise XAPIError on hard failures only when called directly on XAPIClient

Normalised post dict schema
---------------------------
{
    "id":        str,
    "text":      str,
    "timestamp": str,          # ISO 8601
    "likes":     int,
    "comments":  int,          # reply_count
    "shares":    int,          # retweet_count
    "views":     int | None,   # impression_count (not always available)
    "format":    str,          # inferred from tweet content
    "source":    "x_api" | "mock",
}
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

from config import get_settings
from utils.logger import get_logger

logger = get_logger("XAPIClient")

# ── Toggle ────────────────────────────────────────────────────────────────────
# Set to False to skip all network calls and return mock data immediately.
# Useful for local dev / CI when X credentials are not available.

USE_REAL_API: bool = True

# ── Endpoints ─────────────────────────────────────────────────────────────────

_BASE = "https://api.twitter.com/2"
_RECENT_SEARCH  = f"{_BASE}/tweets/search/recent"
_USER_LOOKUP    = f"{_BASE}/users/by/username/{{username}}"
_USER_TWEETS    = f"{_BASE}/users/{{user_id}}/tweets"

# Fields requested on every tweet
_TWEET_FIELDS = (
    "created_at,public_metrics,text,entities,attachments"
)
_EXPANSIONS = "attachments.media_keys"
_MEDIA_FIELDS = "type"

# Free-tier hard cap per request
_FREE_TIER_MAX = 10

# ── Exceptions ────────────────────────────────────────────────────────────────

class XAPIError(Exception):
    """Non-recoverable X API error (bad credentials, user not found, etc.)."""
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class XRateLimitError(XAPIError):
    """HTTP 429 — caller should fall back to mock data."""
    def __init__(self, reset_at: str | None = None):
        msg = "X API rate limit exceeded"
        if reset_at:
            msg += f" (resets at {reset_at})"
        super().__init__(msg, status_code=429)
        self.reset_at = reset_at


# ── Client ────────────────────────────────────────────────────────────────────

class XAPIClient:
    """
    Thin async wrapper around the X v2 API.
    Instantiate with a bearer token; all methods are coroutines.
    """

    def __init__(self, bearer_token: str, timeout: float = 10.0):
        if not bearer_token:
            raise XAPIError("X_BEARER_TOKEN is not set.")
        self._headers = {
            "Authorization": f"Bearer {bearer_token}",
            "User-Agent": "MultiAgentAI/1.0",
        }
        self._timeout = timeout

    # ── Public methods ────────────────────────────────────────────────────

    async def fetch_user_posts(
        self,
        username: str,
        max_results: int = _FREE_TIER_MAX,
    ) -> list[dict[str, Any]]:
        """
        Fetch recent tweets from a public user timeline.
        Returns normalised post dicts.
        """
        max_results = min(max_results, _FREE_TIER_MAX)
        logger.info("x_api_fetch_user", username=username, max_results=max_results)

        user_id = await self._resolve_user_id(username)
        params = {
            "max_results":  max_results,
            "tweet.fields": _TWEET_FIELDS,
            "expansions":   _EXPANSIONS,
            "media.fields": _MEDIA_FIELDS,
            "exclude":      "retweets,replies",
        }
        data = await self._get(_USER_TWEETS.format(user_id=user_id), params)
        tweets = data.get("data") or []
        logger.info("x_api_user_tweets_fetched", username=username, count=len(tweets))
        return [_normalise(t) for t in tweets]

    async def fetch_search_posts(
        self,
        query: str,
        max_results: int = _FREE_TIER_MAX,
    ) -> list[dict[str, Any]]:
        """
        Search recent tweets (last 7 days on free tier).
        Returns normalised post dicts.
        """
        max_results = min(max_results, _FREE_TIER_MAX)
        logger.info("x_api_search", query=query, max_results=max_results)

        params = {
            "query":        f"{query} -is:retweet lang:en",
            "max_results":  max_results,
            "tweet.fields": _TWEET_FIELDS,
            "expansions":   _EXPANSIONS,
            "media.fields": _MEDIA_FIELDS,
        }
        data = await self._get(_RECENT_SEARCH, params)
        tweets = data.get("data") or []
        logger.info("x_api_search_fetched", query=query, count=len(tweets))
        return [_normalise(t) for t in tweets]

    # ── Internal ──────────────────────────────────────────────────────────

    async def _resolve_user_id(self, username: str) -> str:
        data = await self._get(_USER_LOOKUP.format(username=username), {})
        user = data.get("data")
        if not user:
            raise XAPIError(f"User '@{username}' not found on X.", status_code=404)
        return user["id"]

    async def _get(self, url: str, params: dict) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            try:
                resp = await client.get(url, headers=self._headers, params=params)
            except httpx.TimeoutException as exc:
                raise XAPIError(f"X API request timed out: {exc}") from exc
            except httpx.RequestError as exc:
                raise XAPIError(f"X API network error: {exc}") from exc

        _check_response(resp)
        return resp.json()


# ── Response validation ───────────────────────────────────────────────────────

def _check_response(resp: httpx.Response) -> None:
    if resp.status_code == 429:
        reset_at = resp.headers.get("x-rate-limit-reset")
        if reset_at:
            try:
                reset_dt = datetime.fromtimestamp(int(reset_at), tz=timezone.utc)
                reset_at = reset_dt.isoformat()
            except (ValueError, OSError):
                pass
        raise XRateLimitError(reset_at=reset_at)

    if resp.status_code == 401:
        raise XAPIError("Invalid or expired X Bearer Token.", status_code=401)

    if resp.status_code == 403:
        raise XAPIError(
            "X API access forbidden. Check your app permissions and plan.",
            status_code=403,
        )

    if resp.status_code == 404:
        raise XAPIError("X API resource not found.", status_code=404)

    if not resp.is_success:
        try:
            detail = resp.json().get("detail") or resp.text[:200]
        except Exception:
            detail = resp.text[:200]
        raise XAPIError(
            f"X API error {resp.status_code}: {detail}",
            status_code=resp.status_code,
        )


# ── Normalisation ─────────────────────────────────────────────────────────────

def _normalise(tweet: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw v2 tweet object to the pipeline's post dict schema."""
    metrics = tweet.get("public_metrics") or {}
    text    = tweet.get("text", "")

    return {
        "id":        tweet.get("id", ""),
        "text":      text,
        "timestamp": tweet.get("created_at", ""),
        "likes":     metrics.get("like_count", 0),
        "comments":  metrics.get("reply_count", 0),
        "shares":    metrics.get("retweet_count", 0),
        "views":     metrics.get("impression_count"),   # None if not available
        "format":    _infer_format(tweet),
        "source":    "x_api",
    }


def _infer_format(tweet: dict[str, Any]) -> str:
    text = tweet.get("text", "").lower()
    attachments = tweet.get("attachments") or {}
    entities    = tweet.get("entities") or {}

    if attachments.get("media_keys"):
        return "image"
    if any(u.get("expanded_url", "").startswith("https://t.co") for u in entities.get("urls", [])):
        return "link"
    if len(text) > 280:
        return "long-form"
    if text.count("\n") >= 3:
        return "thread"
    return "short-text"


# ── Mock data ─────────────────────────────────────────────────────────────────

_MOCK_POSTS: list[dict[str, Any]] = [
    {
        "id": "mock_001",
        "text": "Just shipped a new feature using LangGraph — multi-agent pipelines are genuinely fun to build. Thread below 🧵",
        "timestamp": "2024-05-01T10:00:00Z",
        "likes": 312, "comments": 47, "shares": 89, "views": 14200,
        "format": "thread", "source": "mock",
    },
    {
        "id": "mock_002",
        "text": "Hot take: RAG is still underrated for production AI apps. Most teams jump to fine-tuning too early.",
        "timestamp": "2024-05-02T14:30:00Z",
        "likes": 528, "comments": 93, "shares": 141, "views": 22100,
        "format": "short-text", "source": "mock",
    },
    {
        "id": "mock_003",
        "text": "Here's what I learned after 6 months of building with GPT-4o in production:\n\n1. Prompt caching saves real money\n2. Structured outputs > JSON mode\n3. Evals are non-negotiable",
        "timestamp": "2024-05-03T09:15:00Z",
        "likes": 874, "comments": 112, "shares": 203, "views": 38500,
        "format": "thread", "source": "mock",
    },
    {
        "id": "mock_004",
        "text": "The best AI products I've seen in 2024 all share one trait: they make the AI invisible. The UX is the product.",
        "timestamp": "2024-05-04T16:45:00Z",
        "likes": 1203, "comments": 178, "shares": 356, "views": 51000,
        "format": "short-text", "source": "mock",
    },
    {
        "id": "mock_005",
        "text": "New blog post: How we cut our LLM costs by 60% without sacrificing quality. Link in bio 👇",
        "timestamp": "2024-05-05T11:00:00Z",
        "likes": 445, "comments": 67, "shares": 122, "views": 19800,
        "format": "link", "source": "mock",
    },
    {
        "id": "mock_006",
        "text": "Vector databases explained in 60 seconds:\n\n- Store embeddings, not raw text\n- Similarity search via cosine/dot product\n- Great for semantic search & RAG\n- Pinecone, Weaviate, pgvector are solid choices",
        "timestamp": "2024-05-06T08:00:00Z",
        "likes": 692, "comments": 84, "shares": 198, "views": 29300,
        "format": "thread", "source": "mock",
    },
    {
        "id": "mock_007",
        "text": "Reminder: your AI agent doesn't need to be autonomous to be useful. Supervised agents with human-in-the-loop are often the right call.",
        "timestamp": "2024-05-07T13:20:00Z",
        "likes": 389, "comments": 55, "shares": 97, "views": 16700,
        "format": "short-text", "source": "mock",
    },
    {
        "id": "mock_008",
        "text": "We just open-sourced our internal prompt testing framework. 500 stars in 24 hours — wasn't expecting that 🙏",
        "timestamp": "2024-05-08T17:00:00Z",
        "likes": 1567, "comments": 234, "shares": 412, "views": 67400,
        "format": "short-text", "source": "mock",
    },
    {
        "id": "mock_009",
        "text": "Unpopular opinion: most AI startups are building wrappers, not products. The moat is in the data and the workflow, not the model.",
        "timestamp": "2024-05-09T10:45:00Z",
        "likes": 2103, "comments": 318, "shares": 589, "views": 88200,
        "format": "short-text", "source": "mock",
    },
    {
        "id": "mock_010",
        "text": "Just crossed 10k followers. Thanks for following along on this AI/ML journey. More deep dives coming this month 🚀",
        "timestamp": "2024-05-10T12:00:00Z",
        "likes": 934, "comments": 143, "shares": 67, "views": 41000,
        "format": "short-text", "source": "mock",
    },
]


def _get_mock_posts(username: str, max_results: int) -> list[dict[str, Any]]:
    """Return a slice of mock posts tagged with the requested username."""
    posts = _MOCK_POSTS[:max_results]
    # Stamp the username so callers can trace the source
    return [{**p, "username": username} for p in posts]


# ── Top-level convenience function ────────────────────────────────────────────

async def fetch_user_posts(
    username: str,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch recent posts for a given X username.

    Behaviour
    ---------
    - If USE_REAL_API is False  → returns mock data immediately.
    - If USE_REAL_API is True   → calls the live X v2 API.
      On any failure (rate limit, bad token, network error, empty response)
      it logs a warning and falls back to mock data — never raises.

    Parameters
    ----------
    username    : X handle without the '@'
    max_results : number of posts to return (capped at 20; free tier max is 10)

    Returns
    -------
    List of normalised post dicts (see module docstring for schema).
    """
    max_results = max(1, min(max_results, 20))

    if not USE_REAL_API:
        logger.info("x_api_mock_mode", username=username, max_results=max_results)
        return _get_mock_posts(username, max_results)

    settings = get_settings()
    if not settings.x_bearer_token:
        logger.warning("x_api_no_token_fallback", username=username)
        return _get_mock_posts(username, max_results)

    try:
        client = XAPIClient(bearer_token=settings.x_bearer_token)
        posts  = await client.fetch_user_posts(username=username, max_results=max_results)

        if not posts:
            logger.warning("x_api_empty_response_fallback", username=username)
            return _get_mock_posts(username, max_results)

        logger.info("x_api_fetch_success", username=username, count=len(posts))
        return posts

    except XRateLimitError as exc:
        logger.warning("x_api_rate_limit_fallback", username=username, error=str(exc))
    except XAPIError as exc:
        logger.warning("x_api_error_fallback", username=username, error=str(exc))
    except Exception as exc:  # noqa: BLE001 — safety net, never crash the pipeline
        logger.error("x_api_unexpected_fallback", username=username, error=str(exc))

    return _get_mock_posts(username, max_results)
