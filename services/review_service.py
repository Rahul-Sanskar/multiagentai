"""
Review Service
--------------
Business logic for the post review lifecycle.

Key responsibility: targeted regeneration — only the relevant agent
is called when a single field needs updating.

Supported update actions
------------------------
  "rewrite_post"        → CopyAgent only
  "regenerate_hashtags" → HashtagAgent only
  "regenerate_visual"   → VisualAgent only
  "regenerate_all"      → all three agents (full re-creation)
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from agents.content_context import ContentContext
from agents.copy_agent import CopyAgent
from agents.hashtag_agent import HashtagAgent
from agents.visual_agent import VisualAgent
from db import review_repository as repo
from db.models import PostReview
from orchestrator.content_creation_orchestrator import (
    ContentCreationOrchestrator,
    _merge,
)
from utils.logger import get_logger
from utils.retry import RetryConfig, with_retry

logger = get_logger("ReviewService")

# Agent singletons — shared, stateless
_copy    = CopyAgent()
_hashtag = HashtagAgent()
_visual  = VisualAgent()
_creator = ContentCreationOrchestrator()

_CREATION_RETRY = RetryConfig(max_attempts=2, base_delay=0.3)

# Maps action name → which fields it touches
_ACTION_FIELDS: dict[str, list[str]] = {
    "rewrite_post":        ["post"],
    "regenerate_hashtags": ["hashtags"],
    "regenerate_visual":   ["visual_prompt", "negative_prompt"],
    "regenerate_all":      ["post", "hashtags", "visual_prompt", "negative_prompt"],
}


# ── Create ────────────────────────────────────────────────────────────────────

async def create_review(
    db: AsyncSession,
    ctx: ContentContext,
) -> dict[str, Any]:
    """Generate content via all three agents and persist as a pending review."""
    package = await with_retry(
        _creator.create,
        args=(ctx,),
        config=_CREATION_RETRY,
    )
    review = await repo.create(
        db,
        post=package["post"],
        hashtags=package["hashtags"],
        visual_prompt=package["visual_prompt"],
        negative_prompt=package.get("negative_prompt", ""),
        context=ctx.to_dict(),
        platform=ctx.platform,
        tone=ctx.tone,
        topic=ctx.topic,
    )
    logger.info("review_created", id=review.id, topic=ctx.topic)
    return repo.deserialise(review)


# ── Status transitions ────────────────────────────────────────────────────────

async def set_status(
    db: AsyncSession,
    review_id: int,
    status: str,
    note: str | None = None,
) -> dict[str, Any]:
    review = await _require(db, review_id)
    await repo.set_status(db, review, status, note)
    logger.info("review_status_updated", id=review_id, status=status)
    return repo.deserialise(review)


# ── Targeted regeneration ─────────────────────────────────────────────────────

async def regenerate(
    db: AsyncSession,
    review_id: int,
    action: str,
    note: str = "",
    context_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Regenerate only the field(s) indicated by `action`.
    Only the relevant agent is invoked — others are untouched.

    Parameters
    ----------
    action            : one of the keys in _ACTION_FIELDS
    note              : reviewer comment stored in revision_history
    context_overrides : optional dict to patch the stored ContentContext
                        (e.g. change tone before rewriting the post)
    """
    if action not in _ACTION_FIELDS:
        raise ValueError(
            f"Unknown action '{action}'. Valid: {list(_ACTION_FIELDS.keys())}"
        )

    review = await _require(db, review_id)
    ctx = _load_context(review, context_overrides)
    ctx_dict = ctx.to_dict()

    fields_to_update = _ACTION_FIELDS[action]
    logger.info("regenerating", id=review_id, action=action, fields=fields_to_update)

    # ── Dispatch only the needed agent(s) ─────────────────────────────────
    if action == "regenerate_all":
        package = await _creator.create(ctx)
        for field in fields_to_update:
            await repo.apply_field_update(db, review, field, package[field], note)
        # also update stored context if overrides were given
        if context_overrides:
            review.context_json = json.dumps(ctx.to_dict())

    elif action == "rewrite_post":
        raw = await _copy.run(ctx.topic, ctx_dict)
        out = json.loads(raw)
        await repo.apply_field_update(db, review, "post", out["post"], note)
        if context_overrides:
            review.context_json = json.dumps(ctx.to_dict())

    elif action == "regenerate_hashtags":
        raw = await _hashtag.run(ctx.topic, ctx_dict)
        out = json.loads(raw)
        await repo.apply_field_update(db, review, "hashtags", out["hashtags"], note)

    elif action == "regenerate_visual":
        raw = await _visual.run(ctx.topic, ctx_dict)
        out = json.loads(raw)
        await repo.apply_field_update(db, review, "visual_prompt", out["visual_prompt"], note)
        await repo.apply_field_update(db, review, "negative_prompt", out.get("negative_prompt", ""), note)

    logger.info("regeneration_complete", id=review_id, action=action)
    return repo.deserialise(review)


# ── Manual field edit (human writes the value directly) ──────────────────────

async def manual_edit(
    db: AsyncSession,
    review_id: int,
    field: str,
    value: Any,
    note: str = "",
) -> dict[str, Any]:
    """
    Accept a human-supplied value for a single field without calling any agent.
    Useful for minor copy tweaks that don't need a full regeneration.
    """
    allowed = {"post", "hashtags", "visual_prompt", "negative_prompt", "reviewer_note"}
    if field not in allowed:
        raise ValueError(f"Field '{field}' is not editable. Allowed: {allowed}")

    review = await _require(db, review_id)
    await repo.apply_field_update(db, review, field, value, note)
    logger.info("manual_edit", id=review_id, field=field)
    return repo.deserialise(review)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _require(db: AsyncSession, review_id: int) -> PostReview:
    review = await repo.get(db, review_id)
    if not review:
        raise KeyError(f"PostReview {review_id} not found.")
    return review


def _load_context(
    review: PostReview,
    overrides: dict[str, Any] | None,
) -> ContentContext:
    base = json.loads(review.context_json)
    if overrides:
        base.update(overrides)
    return ContentContext.from_dict(base)
