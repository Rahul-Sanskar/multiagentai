from datetime import datetime
from sqlalchemy import String, DateTime, Text, Float, Integer, func
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
    field_versions: JSON list of revision snapshots  [{field, old, new, note, ts}]
    """
    __tablename__ = "post_reviews"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Content fields — each independently updatable
    post: Mapped[str] = mapped_column(Text, nullable=False)
    hashtags: Mapped[str] = mapped_column(Text, nullable=False)          # JSON array string
    visual_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    negative_prompt: Mapped[str] = mapped_column(Text, default="")

    # Context snapshot — needed to regenerate individual fields
    context_json: Mapped[str] = mapped_column(Text, nullable=False)      # JSON of ContentContext

    # Review state
    status: Mapped[str] = mapped_column(String(20), default="pending")   # pending|approved|revision
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Metadata
    platform: Mapped[str] = mapped_column(String(50), default="")
    tone: Mapped[str] = mapped_column(String(50), default="")
    topic: Mapped[str] = mapped_column(Text, default="")

    # Audit trail — list of {field, old_value, new_value, note, timestamp}
    revision_history: Mapped[str] = mapped_column(Text, default="[]")    # JSON array string

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PublishJob(Base):
    """
    Tracks one publish attempt for one platform.
    A single /publish call creates N jobs (one per platform).

    status lifecycle:  queued → posted | failed
    """
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    review_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    platform: Mapped[str] = mapped_column(String(50), nullable=False)

    # queued | posted | failed
    status: Mapped[str] = mapped_column(String(20), default="queued")

    post_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
