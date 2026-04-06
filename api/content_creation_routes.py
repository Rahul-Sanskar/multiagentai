"""
Content Creation routes
-----------------------
POST /api/v1/content/create        — single post package
POST /api/v1/content/batch         — multiple topics at once
"""
from typing import Any
from fastapi import APIRouter
from pydantic import BaseModel, Field

from agents.content_context import ContentContext
from orchestrator.content_creation_orchestrator import content_creation_orchestrator

router = APIRouter(prefix="/api/v1/content", tags=["content-creation"])


class CreateRequest(BaseModel):
    topic: str
    tone: str = "informational"
    platform: str = "Instagram"
    audience: str = "general"
    keywords: list[str] = Field(default_factory=list)
    brand_voice: str = ""
    example_posts: list[str] = Field(default_factory=list)


class ContentPackage(BaseModel):
    post: str
    hashtags: list[str]
    visual_prompt: str
    negative_prompt: str
    metadata: dict[str, Any]


@router.post("/create", response_model=ContentPackage)
async def create_content(body: CreateRequest) -> dict[str, Any]:
    ctx = ContentContext(**body.model_dump())
    return await content_creation_orchestrator.create(ctx)


@router.post("/batch", response_model=list[ContentPackage])
async def create_batch(body: list[CreateRequest]) -> list[dict[str, Any]]:
    contexts = [ContentContext(**r.model_dump()) for r in body]
    return await content_creation_orchestrator.create_batch(contexts)
