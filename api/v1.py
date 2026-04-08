"""
Pipeline API — v1
-----------------
Six production-ready endpoints covering the full content pipeline:

  POST /api/v1/analyze-profile
  POST /api/v1/analyze-competitors
  POST /api/v1/generate-calendar
  POST /api/v1/generate-content
  POST /api/v1/review-content
  POST /api/v1/publish

All responses use the ApiResponse[T] envelope:
  { "success": true, "data": {...}, "request_id": "...", "timestamp": "..." }

Errors use ErrorResponse:
  { "success": false, "error": { "code": "...", "message": "..." }, ... }
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from agents.competitor_analysis_agent import CompetitorAnalysisAgent
from agents.content_context import ContentContext
from agents.profile_intelligence_agent import ProfileIntelligenceAgent
from api.schemas_v1 import (
    AnalyzeCompetitorsRequest,
    AnalyzeCompetitorsResponse,
    AnalyzeProfileRequest,
    AnalyzeProfileResponse,
    ApiResponse,
    GenerateCalendarRequest,
    GenerateCalendarResponse,
    GenerateContentRequest,
    GenerateContentResponse,
    PipelineStageResult,
    PublishRequest,
    PublishResponse,
    ReviewContentRequest,
    ReviewContentResponse,
    PipelineRunRequest,
    PipelineRunResponse,
)
from db.review_repository import get as get_review
from db.session import get_db
from orchestrator.calendar_orchestrator import calendar_orchestrator
from orchestrator.content_creation_orchestrator import content_creation_orchestrator
from services import review_service
from services.publish_service import publish
from utils.logger import get_logger
from orchestrator.pipeline_orchestrator import pipeline_orchestrator

router = APIRouter(prefix="/api/v1", tags=["pipeline"])
logger = get_logger("api.v1")

# Agent singletons
_profile_agent    = ProfileIntelligenceAgent()
_competitor_agent = CompetitorAnalysisAgent()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ok(request: Request, data: Any) -> JSONResponse:
    """Wrap data in the standard success envelope."""
    request_id = getattr(request.state, "request_id", "")
    body = ApiResponse(data=data, request_id=request_id)
    return JSONResponse(status_code=status.HTTP_200_OK, content=body.model_dump())


def _created(request: Request, data: Any) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "")
    body = ApiResponse(data=data, request_id=request_id)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=body.model_dump())


# ── POST /analyze-profile ─────────────────────────────────────────────────────

@router.post(
    "/analyze-profile",
    summary="Analyze social media posts to build a profile report",
    response_description="Writing style, topics, posting frequency, and engagement summary",
)
async def analyze_profile(body: AnalyzeProfileRequest, request: Request):
    """
    Accepts a list of social media posts and returns a full profile intelligence
    report: writing style, topic clusters, posting frequency, and engagement stats.
    """
    logger.info("analyze_profile", post_count=len(body.posts),
                request_id=getattr(request.state, "request_id", ""))

    posts = [p.model_dump() for p in body.posts]
    report = _profile_agent.analyze(posts)

    logger.info("analyze_profile_complete", request_id=getattr(request.state, "request_id", ""))
    return _ok(request, report)


# ── POST /analyze-competitors ─────────────────────────────────────────────────

@router.post(
    "/analyze-competitors",
    summary="Compare profile against competitor posts",
    response_description="Content gaps, trending topics, and high-performing formats",
)
async def analyze_competitors(body: AnalyzeCompetitorsRequest, request: Request):
    """
    Takes a profile report (from /analyze-profile) and a list of competitor posts.
    Returns content gaps, trending topics weighted by engagement, and top formats.
    """
    logger.info("analyze_competitors", competitor_posts=len(body.competitor_posts),
                request_id=getattr(request.state, "request_id", ""))

    competitor_posts = [p.model_dump() for p in body.competitor_posts]
    report = _competitor_agent.analyze(body.profile_report, competitor_posts)

    logger.info("analyze_competitors_complete", request_id=getattr(request.state, "request_id", ""))
    return _ok(request, report)


# ── POST /generate-calendar ───────────────────────────────────────────────────

@router.post(
    "/generate-calendar",
    summary="Generate a 14-day content calendar",
    response_description="Session ID and calendar entries with topic, platform, format, and time",
    status_code=201,
)
async def generate_calendar(body: GenerateCalendarRequest, request: Request):
    """
    Generates a content calendar from profile + competitor reports.
    Returns a session_id you can use with the calendar HITL endpoints
    to apply feedback and lock/unlock entries.
    """
    logger.info("generate_calendar", days=body.days,
                request_id=getattr(request.state, "request_id", ""))

    session = await calendar_orchestrator.generate(
        profile_report=body.profile_report,
        competitor_report=body.competitor_report,
        start_date=body.start_date,
        days=body.days,
    )

    data = GenerateCalendarResponse(
        session_id=session.session_id,
        days=len(session.calendar),
        calendar=session.calendar,
    )
    logger.info("generate_calendar_complete", session_id=session.session_id,
                request_id=getattr(request.state, "request_id", ""))
    return _created(request, data.model_dump())


# ── POST /generate-content ────────────────────────────────────────────────────

@router.post(
    "/generate-content",
    summary="Generate post copy, hashtags, and visual prompt",
    response_description="Complete content package ready for review",
    status_code=201,
)
async def generate_content(body: GenerateContentRequest, request: Request):
    """
    Runs CopyAgent, HashtagAgent, and VisualAgent in parallel.
    Returns a single content package: post text, hashtags, and an image-gen prompt.
    """
    logger.info("generate_content", topic=body.topic, platform=body.platform,
                tone=body.tone, request_id=getattr(request.state, "request_id", ""))

    ctx = ContentContext(**body.model_dump())
    package = await content_creation_orchestrator.create(ctx)

    data = GenerateContentResponse(
        post=package["post"],
        hashtags=package["hashtags"],
        visual_prompt=package["visual_prompt"],
        negative_prompt=package.get("negative_prompt", ""),
        metadata=package["metadata"],
    )
    logger.info("generate_content_complete", topic=body.topic,
                request_id=getattr(request.state, "request_id", ""))
    return _created(request, data.model_dump())


# ── POST /review-content ──────────────────────────────────────────────────────

@router.post(
    "/review-content",
    summary="Create a reviewable content package stored in the database",
    response_description="Persisted review with status=pending",
    status_code=201,
)
async def review_content(
    body: ReviewContentRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Generates content (same as /generate-content) and persists it as a
    PostReview with status=pending. Use the /api/v1/reviews endpoints to
    approve, request revision, or trigger targeted regeneration.
    """
    logger.info("review_content", topic=body.topic, platform=body.platform,
                request_id=getattr(request.state, "request_id", ""))

    ctx = ContentContext(**body.model_dump())
    review = await review_service.create_review(db, ctx)

    data = ReviewContentResponse(**review)
    logger.info("review_content_created", review_id=review["id"],
                request_id=getattr(request.state, "request_id", ""))
    return _created(request, data.model_dump())


# ── POST /publish ─────────────────────────────────────────────────────────────

@router.post(
    "/publish",
    summary="Publish an approved review to one or more platforms (mock)",
    response_description="Per-platform publish results with status and post URL",
)
async def publish_content(
    body: PublishRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Publishes an approved PostReview to the requested platforms.
    Currently a mock — replace _mock_publish_to_platform() in
    services/publish_service.py with real platform API calls.

    - Only reviews with status=approved can be published.
    - Pass scheduled_at (ISO datetime) to schedule instead of publishing immediately.
    """
    logger.info("publish", review_id=body.review_id, platforms=body.platforms,
                scheduled_at=body.scheduled_at,
                request_id=getattr(request.state, "request_id", ""))

    review = await get_review(db, body.review_id)
    if not review:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Review {body.review_id} not found.")

    results = await publish(db, review, body.platforms, body.scheduled_at)

    published = sum(1 for r in results if r["status"] in ("posted", "queued"))
    failed    = sum(1 for r in results if r["status"] == "failed")

    data = PublishResponse(
        review_id=body.review_id,
        results=results,
        published_count=published,
        failed_count=failed,
    )
    logger.info("publish_complete", review_id=body.review_id,
                published=published, failed=failed,
                request_id=getattr(request.state, "request_id", ""))
    return _ok(request, data.model_dump())


# ── POST /pipeline/run ────────────────────────────────────────────────────────

@router.post(
    "/pipeline/run",
    summary="Run the full content pipeline end-to-end",
    response_description="Aggregated results from all pipeline stages",
    status_code=201,
)
async def run_pipeline(
    body: PipelineRunRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Executes all pipeline stages in sequence without manual intervention:

    1. Profile Analysis
    2. Competitor Analysis
    3. RAG Ingestion (profile + competitor reports)
    4. Calendar Generation (RAG-enriched topics)
    5. Content Creation (one post per calendar entry, keywords from RAG)
    6. Review Creation (all stored as pending)
    7. Auto-approve (if auto_approve=True)
    8. Publish (if auto_approve=True)
    """
    logger.info(
        "pipeline_run_start",
        my_posts=len(body.my_posts),
        competitor_posts=len(body.competitor_posts),
        days=body.days,
        auto_approve=body.auto_approve,
        request_id=getattr(request.state, "request_id", ""),
    )

    my_posts = [p.model_dump() for p in body.my_posts]
    competitor_posts = [p.model_dump() for p in body.competitor_posts]

    # ── Real X data ingestion ─────────────────────────────────────────────
    # Priority: real X API → manual my_posts → built-in mock dataset
    # Never raises — always produces usable posts for the pipeline.
    my_posts_source = "manual"
    if body.x_username:
        from services.x_api_client import fetch_user_posts, USE_REAL_API, _MOCK_POSTS
        from config import get_settings as _gs
        token = _gs().x_bearer_token.strip()
        if token and USE_REAL_API:
            try:
                fetched = await fetch_user_posts(
                    username=body.x_username.lstrip("@"),
                    max_results=10,
                )
                if fetched and fetched[0].get("source") == "x_api":
                    my_posts = fetched
                    my_posts_source = "real_x_api"
                    logger.info("x_data_ingestion_success",
                                username=body.x_username, count=len(my_posts))
                else:
                    # API returned mock (depleted credits / rate limit)
                    # Use whatever the caller provided, or fall back to built-in mock
                    if not my_posts:
                        my_posts = list(_MOCK_POSTS)
                    my_posts_source = "mock"
                    logger.warning("x_data_ingestion_fallback",
                                   username=body.x_username,
                                   reason="API returned mock data — using fallback posts")
            except Exception as exc:
                if not my_posts:
                    my_posts = list(_MOCK_POSTS)
                my_posts_source = "mock"
                logger.warning("x_data_ingestion_error",
                               username=body.x_username, error=str(exc),
                               reason="Falling back to mock posts")
        else:
            logger.info("x_data_ingestion_skipped",
                        reason="X_BEARER_TOKEN not set or USE_REAL_API=False")

    # Final safety net — use built-in mock if still empty
    if not my_posts:
        from services.x_api_client import _MOCK_POSTS
        my_posts = list(_MOCK_POSTS)
        my_posts_source = "mock"
        logger.warning("my_posts_empty_using_mock",
                       reason="No posts provided and X ingestion unavailable")

    result = await pipeline_orchestrator.run(
        my_posts=my_posts,
        competitor_posts=competitor_posts,
        db=db,
        start_date=body.start_date,
        days=body.days,
        platforms=list(body.platforms),
        auto_approve=body.auto_approve,
        rag_query=body.rag_query,
    )

    data = PipelineRunResponse(
        calendar_session_id=result.calendar_session_id,
        calendar_entries=len(result.calendar),
        reviews_created=len(result.reviews),
        publish_jobs=len(result.publish_results),
        stages=[PipelineStageResult(**s.__dict__) for s in result.stages],
        rag_stats=result.rag_stats,
        calendar=result.calendar,
        my_posts_source=my_posts_source,
    )

    logger.info(
        "pipeline_run_complete",
        calendar_entries=data.calendar_entries,
        reviews=data.reviews_created,
        publish_jobs=data.publish_jobs,
        request_id=getattr(request.state, "request_id", ""),
    )
    return _created(request, data.model_dump())
