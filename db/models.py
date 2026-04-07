from datetime import datetime
from sqlalchemy import String, DateTime, Text, Float, Integer, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column
from db.session import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PostReview(Base):
    """
    Stores a generated content package (post + hashtags + visual prompt)
    and tracks its review lifecycle.

    status: pending | approved | revision
    """
    __tablename__ = "post_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    post: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[str] = mapped_column(Text, nullable=False)
    visual_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, default="")
    context_json: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[str] = mapped_column(String(20), default="pending")
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    platform: Mapped[str] = mapped_column(String(50), default="")
    tone: Mapped[str] = mapped_column(String(50), default="")
    topic: Mapped[str] = mapped_column(Text, default="")

    revision_history: Mapped[str] = mapped_column(Text, default="[]")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PublishJob(Base):
    """
    Tracks one publish attempt for one platform.
    status lifecycle: queued → posted | failed
    """
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    post_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # External platform post ID — used to fetch metrics later
    platform_post_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    scheduled_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PostImpact(Base):
    """
    Stores post-publish engagement metrics fetched from the platform.
    """
    __tablename__ = "post_impacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    publish_job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    topic: Mapped[str] = mapped_column(Text, default="")

    impressions: Mapped[int] = mapped_column(Integer, default=0)
    likes: Mapped[int] = mapped_column(Integer, default=0)
    comments: Mapped[int] = mapped_column(Integer, default=0)
    shares: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)

    expected_likes: Mapped[float] = mapped_column(Float, default=0.0)
    expected_comments: Mapped[float] = mapped_column(Float, default=0.0)
    expected_shares: Mapped[float] = mapped_column(Float, default=0.0)

    performance_tag: Mapped[str] = mapped_column(String(20), default="unknown")
    insight_json: Mapped[str] = mapped_column(Text, default="{}")

    fetched_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ScheduledImpact(Base):
    """
    Persists a pending impact-metric fetch so it survives server restarts.

    Lifecycle
    ---------
    pending   → created at publish time, fetch not yet run
    running   → picked up by the background loop
    done      → fetch completed successfully
    failed    → fetch failed after retries

    On startup, all rows with status='pending' whose fetch_after time has
    passed are re-queued automatically.
    """
    __tablename__ = "scheduled_impacts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    publish_job_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)
    topic: Mapped[str] = mapped_column(Text, default="")
    expected_json: Mapped[str] = mapped_column(Text, default="{}")  # {"likes":..., ...}

    # When to run the fetch (absolute UTC datetime)
    fetch_after: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # pending | running | done | failed
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
