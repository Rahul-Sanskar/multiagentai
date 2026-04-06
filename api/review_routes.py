"""
Post Review API
---------------
POST   /api/v1/reviews                          create a new review
GET    /api/v1/reviews                          list reviews (filter by status)
GET    /api/v1/reviews/{id}                     get one review
PATCH  /api/v1/reviews/{id}/status              approve / request revision
POST   /api/v1/reviews/{id}/regenerate          targeted agent regeneration
PATCH  /api/v1/reviews/{id}/edit                manual field edit (no agent)
GET    /api/v1/reviews/{id}/history             revision audit trail
"""
from typing import Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from agents.content_context import ContentContext
from db.session import get_db
from db.review_repository import STATUSES, deserialise, list_all, get
from services import review_service
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/v1/reviews", tags=["reviews"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class CreateReviewRequest(BaseModel):
    topic: str
    tone: str = "informational"
    platform: str = "Instagram"
    audience: str = "general"
    keywords: list[str] = Field(default_factory=list)
    brand_voice: str = ""


class StatusUpdateRequest(BaseModel):
    status: Literal["pending", "approved", "revision"]
    note: str | None = None


class RegenerateRequest(BaseModel):
    action: Literal[
        "rewrite_post",
        "regenerate_hashtags",
        "regenerate_visual",
        "regenerate_all",
    ]
    note: str = ""
    context_overrides: dict[str, Any] | None = None   # e.g. {"tone": "casual"}


class ManualEditRequest(BaseModel):
    field: str
    value: Any
    note: str = ""


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("", status_code=201)
async def create_review(
    body: CreateReviewRequest,
    db: AsyncSession = Depends(get_db),
):
    ctx = ContentContext(**body.model_dump())
    return await review_service.create_review(db, ctx)


@router.get("")
async def list_reviews(
    status: str | None = Query(default=None, description="Filter by status: pending|approved|revision"),
    limit: int = Query(default=20, le=100),
    offset: int = Query(default=0),
    db: AsyncSession = Depends(get_db),
):
    if status and status not in STATUSES:
        raise HTTPException(400, f"Invalid status. Must be one of {STATUSES}")
    rows = await list_all(db, status=status, limit=limit, offset=offset)
    return [deserialise(r) for r in rows]


@router.get("/{review_id}")
async def get_review(review_id: int, db: AsyncSession = Depends(get_db)):
    row = await get(db, review_id)
    if not row:
        raise HTTPException(404, "Review not found.")
    return deserialise(row)


@router.patch("/{review_id}/status")
async def update_status(
    review_id: int,
    body: StatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await review_service.set_status(db, review_id, body.status, body.note)
    except KeyError as e:
        raise HTTPException(404, str(e))


@router.post("/{review_id}/regenerate")
async def regenerate(
    review_id: int,
    body: RegenerateRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await review_service.regenerate(
            db, review_id, body.action, body.note, body.context_overrides
        )
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.patch("/{review_id}/edit")
async def manual_edit(
    review_id: int,
    body: ManualEditRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await review_service.manual_edit(db, review_id, body.field, body.value, body.note)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/{review_id}/history")
async def get_history(review_id: int, db: AsyncSession = Depends(get_db)):
    import json
    row = await get(db, review_id)
    if not row:
        raise HTTPException(404, "Review not found.")
    return json.loads(row.revision_history or "[]")
