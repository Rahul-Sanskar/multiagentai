"""
Dedicated routes for the intelligence agents.
POST /api/v1/intelligence/profile
POST /api/v1/intelligence/competitor
"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Any

from agents.profile_intelligence_agent import ProfileIntelligenceAgent
from agents.competitor_analysis_agent import CompetitorAnalysisAgent

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])

_profile_agent = ProfileIntelligenceAgent()
_competitor_agent = CompetitorAnalysisAgent()


class Post(BaseModel):
    text: str
    timestamp: str | None = None
    likes: int | None = None
    comments: int | None = None
    shares: int | None = None
    views: int | None = None
    format: str | None = None


class ProfileRequest(BaseModel):
    posts: list[Post]


class CompetitorRequest(BaseModel):
    profile_report: dict[str, Any]
    competitor_posts: list[Post]


@router.post("/profile")
async def analyze_profile(body: ProfileRequest) -> dict[str, Any]:
    posts = [p.model_dump() for p in body.posts]
    return _profile_agent.analyze(posts)


@router.post("/competitor")
async def analyze_competitor(body: CompetitorRequest) -> dict[str, Any]:
    competitor_posts = [p.model_dump() for p in body.competitor_posts]
    return _competitor_agent.analyze(body.profile_report, competitor_posts)
