"""
Data Loader
-----------
Single entry point for loading post data in the e2e test.

Toggle
------
    USE_REAL_API = True   → fetch from X API, fall back to mock on any error
    USE_REAL_API = False  → return mock dataset immediately

Fallback chain
--------------
    X API success          → return real posts
    XRateLimitError        → warn + return mock (never crash)
    XAPIError (bad token)  → warn + return mock
    Any other exception    → warn + return mock

The function always returns a non-empty list of post dicts.
"""
from __future__ import annotations

import os
from typing import Any

from utils.logger import get_logger

logger = get_logger("DataLoader")


# ── Mock datasets (used when USE_REAL_API=False or API fails) ─────────────────

MOCK_MY_POSTS: list[dict[str, Any]] = [
    {
        "text": "Just deployed a multi-agent system using LangGraph. The future of AI apps is agentic.",
        "timestamp": "2024-01-01T09:00:00", "likes": 312, "comments": 47, "shares": 89, "views": 6800,
    },
    {
        "text": "RAG pipelines are still misunderstood. It's not just retrieval, it's grounding + reasoning.",
        "timestamp": "2024-01-03T10:30:00", "likes": 528, "comments": 91, "shares": 143, "views": 11200,
    },
    {
        "text": "Built an LSTM anomaly detection model for ICS systems. Results look promising.",
        "timestamp": "2024-01-05T08:00:00", "likes": 204, "comments": 38, "shares": 52, "views": 4300,
    },
    {
        "text": "Consistency > virality. Posting daily is the real growth hack.",
        "timestamp": "2024-01-07T11:00:00", "likes": 741, "comments": 112, "shares": 198, "views": 15600,
    },
    {
        "text": "Fine-tuned a small LLM on domain-specific data. 3x better than GPT-4 on our eval set.",
        "timestamp": "2024-01-09T09:30:00", "likes": 389, "comments": 64, "shares": 107, "views": 8100,
    },
]

MOCK_COMPETITOR_POSTS: list[dict[str, Any]] = [
    # Competitor 1 — AI tools & productivity
    {
        "text": "Thread: 7 AI tools that replaced half my workflow in 2024. Save this.",
        "timestamp": "2024-01-02T09:00:00", "likes": 890, "comments": 134, "shares": 312,
        "views": 18000, "format": "thread",
    },
    {
        "text": "Tutorial: Build a GPT-4 powered Notion assistant in 30 minutes. Step-by-step.",
        "timestamp": "2024-01-04T10:00:00", "likes": 1120, "comments": 201, "shares": 445,
        "views": 24000, "format": "tutorial",
    },
    # Competitor 2 — Deep technical ML
    {
        "text": "Why attention mechanisms still outperform state-space models on long-context tasks. A deep dive.",
        "timestamp": "2024-01-02T11:00:00", "likes": 743, "comments": 167, "shares": 289,
        "views": 16200, "format": "long-form",
    },
    {
        "text": "Quantisation explained: INT4 vs INT8 vs FP16. When to use each and what you lose.",
        "timestamp": "2024-01-05T09:00:00", "likes": 612, "comments": 143, "shares": 231,
        "views": 13800, "format": "long-form",
    },
    # Competitor 3 — Startup + AI storytelling
    {
        "text": "We almost ran out of runway at month 8. Here's how an AI-powered pivot saved our startup.",
        "timestamp": "2024-01-03T08:00:00", "likes": 1340, "comments": 287, "shares": 512,
        "views": 29000, "format": "storytelling",
    },
    {
        "text": "From 0 to $1M ARR using AI agents for sales automation. The playbook nobody talks about.",
        "timestamp": "2024-01-06T09:30:00", "likes": 1780, "comments": 341, "shares": 678,
        "views": 38000, "format": "storytelling",
    },
    {
        "text": "I fired our entire outbound team and replaced them with 3 AI agents. Here's what happened.",
        "timestamp": "2024-01-09T08:00:00", "likes": 2100, "comments": 412, "shares": 891,
        "views": 45000, "format": "storytelling",
    },
]


# ── Public API ────────────────────────────────────────────────────────────────

async def load_my_posts(
    use_real_api: bool,
    username: str = "",
    max_results: int = 10,
) -> tuple[list[dict[str, Any]], str]:
    """
    Load own posts.

    Returns
    -------
    (posts, source)  where source is "x_api" | "mock"
    """
    if not use_real_api:
        logger.info("data_loader_mock", target="my_posts")
        return MOCK_MY_POSTS, "mock"

    return await _fetch_with_fallback(
        label="my_posts",
        fetch_coro=_fetch_user(username, max_results),
        fallback=MOCK_MY_POSTS,
    )


async def load_competitor_posts(
    use_real_api: bool,
    queries: list[str] | None = None,
    max_per_query: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    """
    Load competitor posts via search queries.

    Returns
    -------
    (posts, source)  where source is "x_api" | "mock"
    """
    if not use_real_api:
        logger.info("data_loader_mock", target="competitor_posts")
        return MOCK_COMPETITOR_POSTS, "mock"

    default_queries = [
        "AI agents LangGraph -is:retweet",
        "RAG pipeline LLM -is:retweet",
        "AI startup growth -is:retweet",
    ]
    queries = queries or default_queries

    return await _fetch_with_fallback(
        label="competitor_posts",
        fetch_coro=_fetch_search(queries, max_per_query),
        fallback=MOCK_COMPETITOR_POSTS,
    )


# ── Internal helpers ──────────────────────────────────────────────────────────

async def _fetch_with_fallback(
    label: str,
    fetch_coro,
    fallback: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], str]:
    """Run fetch_coro; on any error log a warning and return fallback."""
    from services.x_api_client import XRateLimitError, XAPIError

    try:
        posts = await fetch_coro
        if not posts:
            logger.warning("x_api_empty_response", label=label,
                           reason="API returned 0 posts — using mock data")
            return fallback, "mock"
        logger.info("data_loader_real", label=label, count=len(posts))
        return posts, "x_api"

    except XRateLimitError as exc:
        logger.warning("x_api_rate_limit", label=label, reset_at=exc.reset_at,
                       fallback="mock_data")
        return fallback, "mock"

    except XAPIError as exc:
        logger.warning("x_api_error", label=label, error=str(exc),
                       status_code=exc.status_code, fallback="mock_data")
        return fallback, "mock"

    except Exception as exc:
        logger.warning("x_api_unexpected_error", label=label, error=str(exc),
                       fallback="mock_data")
        return fallback, "mock"


async def _fetch_user(username: str, max_results: int):
    """Coroutine: fetch user timeline."""
    from config import get_settings
    from services.x_api_client import XAPIClient, XAPIError

    settings = get_settings()
    token = settings.x_bearer_token
    if not token:
        raise XAPIError("X_BEARER_TOKEN not configured.")
    if not username:
        raise XAPIError("No username provided for user timeline fetch.")

    client = XAPIClient(bearer_token=token)
    return await client.fetch_user_posts(username=username, max_results=max_results)


async def _fetch_search(queries: list[str], max_per_query: int):
    """Coroutine: run multiple search queries and merge results."""
    from config import get_settings
    from services.x_api_client import XAPIClient, XAPIError

    settings = get_settings()
    token = settings.x_bearer_token
    if not token:
        raise XAPIError("X_BEARER_TOKEN not configured.")

    client = XAPIClient(bearer_token=token)
    all_posts: list[dict] = []
    seen_texts: set[str] = set()

    for query in queries:
        try:
            posts = await client.fetch_search_posts(query=query, max_results=max_per_query)
            for p in posts:
                key = p["text"][:80]
                if key not in seen_texts:
                    seen_texts.add(key)
                    all_posts.append(p)
        except Exception as exc:
            # One query failing shouldn't abort the rest
            logger.warning("x_api_query_failed", query=query, error=str(exc))

    return all_posts
