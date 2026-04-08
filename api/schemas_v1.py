"""
Canonical request/response schemas for the v1 pipeline endpoints.
All responses are wrapped in ApiResponse for consistent envelope shape.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


# ── Envelope ──────────────────────────────────────────────────────────────────

class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T
    request_id: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None


class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
    request_id: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


# ── Shared primitives ─────────────────────────────────────────────────────────

class PostInput(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000)
    timestamp: str | None = None
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    views: int | None = Field(default=None, ge=0)
    format: str | None = None


# ── /analyze-profile ─────────────────────────────────────────────────────────

class AnalyzeProfileRequest(BaseModel):
    posts: list[PostInput] = Field(..., min_length=1, max_length=500)


class WritingStyle(BaseModel):
    tone: str
    avg_sentence_length: float
    avg_post_length_words: float
    avg_post_length_chars: float


class TopicAnalysis(BaseModel):
    top_keywords: list[str]
    clusters: dict[str, list[str]]


class AnalyzeProfileResponse(BaseModel):
    post_count: int
    writing_style: WritingStyle
    topics: TopicAnalysis
    posting_frequency: dict[str, Any]
    engagement: dict[str, Any]


# ── /analyze-competitors ──────────────────────────────────────────────────────

class AnalyzeCompetitorsRequest(BaseModel):
    profile_report: dict[str, Any] = Field(..., description="Output of /analyze-profile")
    competitor_posts: list[PostInput] = Field(..., min_length=1, max_length=500)


class ContentGaps(BaseModel):
    gaps: list[str]
    overlap: list[str]
    unique_to_profile: list[str]


class TrendingTopic(BaseModel):
    keyword: str
    mentions: int
    total_engagement: float
    avg_engagement_per_mention: float


class HighPerformingFormat(BaseModel):
    format: str
    post_count: int
    avg_engagement: float
    total_engagement: float


class AnalyzeCompetitorsResponse(BaseModel):
    competitor_post_count: int
    content_gaps: ContentGaps
    trending_topics: list[TrendingTopic]
    high_performing_formats: list[HighPerformingFormat]
    competitor_engagement: dict[str, Any]
    competitor_writing_style: dict[str, Any]


# ── /generate-calendar ────────────────────────────────────────────────────────

class GenerateCalendarRequest(BaseModel):
    profile_report: dict[str, Any] = Field(..., description="Output of /analyze-profile")
    competitor_report: dict[str, Any] = Field(..., description="Output of /analyze-competitors")
    start_date: str | None = Field(default=None, description="ISO date e.g. 2024-02-01")
    days: int = Field(default=14, ge=1, le=30)

    @field_validator("start_date")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("start_date must be a valid ISO date string (YYYY-MM-DD)")
        return v


class CalendarEntry(BaseModel):
    day: int
    date: str
    platform: str
    format: str
    time: str
    topic: str | None
    source: str | None
    priority: str | None
    locked: bool


class GenerateCalendarResponse(BaseModel):
    session_id: str
    days: int
    calendar: list[CalendarEntry]


# ── /generate-content ─────────────────────────────────────────────────────────

class GenerateContentRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=200)
    tone: Literal["casual", "formal", "promotional", "informational", "inspirational"] = "informational"
    platform: Literal["Instagram", "LinkedIn", "Twitter/X", "TikTok", "YouTube"] = "Instagram"
    audience: str = Field(default="general", max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    brand_voice: str = Field(default="", max_length=200)
    example_posts: list[str] = Field(default_factory=list, max_length=10)


class ContentMetadata(BaseModel):
    tone: str
    platform: str
    word_count: int | None
    hashtag_count: int | None
    aspect_ratio: str | None


class GenerateContentResponse(BaseModel):
    post: str
    hashtags: list[str]
    visual_prompt: str
    negative_prompt: str
    metadata: ContentMetadata


# ── /review-content ───────────────────────────────────────────────────────────

class ReviewContentRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=200)
    tone: Literal["casual", "formal", "promotional", "informational", "inspirational"] = "informational"
    platform: Literal["Instagram", "LinkedIn", "Twitter/X", "TikTok", "YouTube"] = "Instagram"
    audience: str = Field(default="general", max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=20)
    brand_voice: str = Field(default="", max_length=200)
    example_posts: list[str] = Field(default_factory=list, max_length=10)


class RevisionHistoryEntry(BaseModel):
    field: str
    old_value: Any
    new_value: Any
    note: str
    timestamp: str


class ReviewContentResponse(BaseModel):
    id: int
    post: str
    hashtags: list[str]
    visual_prompt: str
    negative_prompt: str
    status: Literal["pending", "approved", "revision"]
    reviewer_note: str | None
    platform: str
    tone: str
    topic: str
    revision_history: list[dict[str, Any]]
    created_at: str | None
    updated_at: str | None


# ── /publish ──────────────────────────────────────────────────────────────────

class PublishRequest(BaseModel):
    review_id: int = Field(..., gt=0)
    platforms: list[Literal["Instagram", "LinkedIn", "Twitter/X", "TikTok", "YouTube"]] = Field(
        ..., min_length=1
    )
    scheduled_at: str | None = Field(
        default=None,
        description="ISO datetime to schedule publish. Omit for immediate (mock).",
    )

    @field_validator("scheduled_at")
    @classmethod
    def validate_scheduled_at(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("scheduled_at must be a valid ISO datetime string")
        return v


class PlatformPublishResult(BaseModel):
    job_id: int
    platform: str
    status: Literal["posted", "queued", "failed"]
    post_url: str | None
    scheduled_at: str | None
    latency_ms: float | None
    message: str


class PublishResponse(BaseModel):
    review_id: int
    results: list[PlatformPublishResult]
    published_count: int
    failed_count: int


# ── /pipeline/run ─────────────────────────────────────────────────────────────

class PipelineRunRequest(BaseModel):
    my_posts: list[PostInput] = Field(
        default_factory=list,
        max_length=500,
        description="Your own social media posts. Ignored if x_username is provided and X_BEARER_TOKEN is set.",
    )
    competitor_posts: list[PostInput] = Field(..., min_length=1, max_length=500,
                                              description="Competitor posts to analyse")
    x_username: str | None = Field(
        default=None,
        description="X (Twitter) handle to fetch real posts from (without @). Requires X_BEARER_TOKEN in .env.",
    )
    start_date: str | None = Field(default=None, description="Calendar start date (YYYY-MM-DD)")
    days: int = Field(default=14, ge=1, le=14)
    platforms: list[Literal["Instagram", "LinkedIn", "Twitter/X", "TikTok", "YouTube"]] = Field(
        default=["Instagram"]
    )
    auto_approve: bool = Field(
        default=False,
        description="Auto-approve all reviews and publish immediately"
    )
    rag_query: str = Field(
        default="trending topics and high engagement content",
        description="Query used to enrich content keywords from RAG index"
    )

    @field_validator("start_date")
    @classmethod
    def validate_date(cls, v: str | None) -> str | None:
        if v is None:
            return v
        try:
            datetime.fromisoformat(v)
        except ValueError:
            raise ValueError("start_date must be a valid ISO date string (YYYY-MM-DD)")
        return v


class PipelineStageResult(BaseModel):
    stage: str
    success: bool
    data: Any = None
    error: str | None = None


class PipelineRunResponse(BaseModel):
    calendar_session_id: str
    calendar_entries: int
    reviews_created: int
    publish_jobs: int
    stages: list[PipelineStageResult]
    rag_stats: dict[str, Any]
    calendar: list[dict[str, Any]] = Field(default_factory=list)
    my_posts_source: str = "manual"   # "real_x_api" | "mock" | "manual"
