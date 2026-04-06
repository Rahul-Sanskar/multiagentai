"""
PostReview repository — all DB access in one place, no business logic.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import PostReview

# Valid statuses
STATUSES = {"pending", "approved", "revision"}


async def create(
    db: AsyncSession,
    post: str,
    hashtags: list[str],
    visual_prompt: str,
    negative_prompt: str,
    context: dict[str, Any],
    platform: str,
    tone: str,
    topic: str,
) -> PostReview:
    row = PostReview(
        post=post,
        hashtags=json.dumps(hashtags),
        visual_prompt=visual_prompt,
        negative_prompt=negative_prompt,
        context_json=json.dumps(context),
        platform=platform,
        tone=tone,
        topic=topic,
        status="pending",
        revision_history="[]",
    )
    db.add(row)
    await db.flush()
    return row


async def get(db: AsyncSession, review_id: int) -> PostReview | None:
    return await db.get(PostReview, review_id)


async def list_all(
    db: AsyncSession,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[PostReview]:
    q = select(PostReview).order_by(PostReview.created_at.desc()).limit(limit).offset(offset)
    if status:
        q = q.where(PostReview.status == status)
    result = await db.execute(q)
    return list(result.scalars().all())


async def set_status(
    db: AsyncSession,
    review: PostReview,
    status: str,
    note: str | None = None,
) -> PostReview:
    if status not in STATUSES:
        raise ValueError(f"Invalid status '{status}'. Must be one of {STATUSES}")
    review.status = status
    if note is not None:
        review.reviewer_note = note
    return review


async def apply_field_update(
    db: AsyncSession,
    review: PostReview,
    field: str,           # "post" | "hashtags" | "visual_prompt"
    new_value: Any,
    note: str = "",
) -> PostReview:
    """Update one content field and append an entry to revision_history."""
    old_value = getattr(review, field)

    # Serialise lists to JSON string for storage
    stored = json.dumps(new_value) if isinstance(new_value, list) else new_value
    setattr(review, field, stored)

    # Append to audit trail
    history: list[dict] = json.loads(review.revision_history or "[]")
    history.append({
        "field": field,
        "old_value": old_value,
        "new_value": stored,
        "note": note,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
    review.revision_history = json.dumps(history)
    review.status = "revision"
    return review


def deserialise(review: PostReview) -> dict[str, Any]:
    """Convert a PostReview ORM row to a clean dict for API responses."""
    return {
        "id": review.id,
        "post": review.post,
        "hashtags": json.loads(review.hashtags),
        "visual_prompt": review.visual_prompt,
        "negative_prompt": review.negative_prompt,
        "status": review.status,
        "reviewer_note": review.reviewer_note,
        "platform": review.platform,
        "tone": review.tone,
        "topic": review.topic,
        "revision_history": json.loads(review.revision_history or "[]"),
        "created_at": review.created_at.isoformat() if review.created_at else None,
        "updated_at": review.updated_at.isoformat() if review.updated_at else None,
    }
