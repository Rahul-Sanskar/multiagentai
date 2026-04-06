"""
Competitor Analysis Agent
--------------------------
Input : profile_report (dict from ProfileIntelligenceAgent)
        competitor_posts (list of post dicts)
Output: structured JSON with content gaps, trending topics, high-performing formats.
"""
from typing import Any

from agents.base_agent import BaseAgent
from utils.nlp_utils import (
    extract_keywords,
    engagement_summary,
    writing_style,
    clean_text,
    tokenize_words,
)


class CompetitorAnalysisAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="CompetitorAnalysisAgent")

    # ── public entry point ────────────────────────────────────────────────

    async def run(self, task: str, context: dict | None = None) -> str:
        import json
        ctx = context or {}
        profile_report = ctx.get("profile_report", {})
        competitor_posts = ctx.get("competitor_posts", [])
        report = self.analyze(profile_report, competitor_posts)
        return json.dumps(report, indent=2, default=str)

    # ── core analysis (sync, reusable) ───────────────────────────────────

    def analyze(
        self,
        profile_report: dict[str, Any],
        competitor_posts: list[dict],
    ) -> dict[str, Any]:
        """
        Compares a profile report against competitor posts and returns
        content gaps, trending topics, and high-performing formats.
        """
        if not competitor_posts:
            return {"error": "No competitor posts provided"}

        self.logger.info("analyzing_competitors", post_count=len(competitor_posts))

        comp_keywords = extract_keywords(
            [p.get("text", "") for p in competitor_posts], top_n=30
        )
        profile_keywords: list[str] = (
            profile_report.get("topics", {}).get("top_keywords", [])
        )

        report = {
            "competitor_post_count": len(competitor_posts),
            "content_gaps": self._content_gaps(profile_keywords, comp_keywords),
            "trending_topics": self._trending_topics(competitor_posts, top_n=10),
            "high_performing_formats": self._high_performing_formats(competitor_posts),
            "competitor_engagement": engagement_summary(competitor_posts),
            "competitor_writing_style": writing_style(competitor_posts),
        }

        self.logger.info("competitor_analysis_complete")
        return report

    # ── helpers ───────────────────────────────────────────────────────────

    @staticmethod
    def _content_gaps(
        profile_keywords: list[str],
        competitor_keywords: list[str],
    ) -> dict[str, Any]:
        """Topics competitors cover that the profile does not."""
        profile_set = set(profile_keywords)
        comp_set = set(competitor_keywords)

        gaps = sorted(comp_set - profile_set)
        overlap = sorted(profile_set & comp_set)
        unique_to_profile = sorted(profile_set - comp_set)

        return {
            "gaps": gaps,                          # competitor covers, profile doesn't
            "overlap": overlap,                    # both cover
            "unique_to_profile": unique_to_profile,  # profile covers, competitor doesn't
        }

    @staticmethod
    def _trending_topics(posts: list[dict], top_n: int = 10) -> list[dict[str, Any]]:
        """
        Identifies trending topics by weighting keyword frequency
        against engagement (likes + comments + shares).
        """
        from collections import defaultdict

        keyword_engagement: dict[str, float] = defaultdict(float)
        keyword_count: dict[str, int] = defaultdict(int)

        for post in posts:
            text = post.get("text", "")
            tokens = tokenize_words(clean_text(text))
            engagement = (
                float(post.get("likes", 0) or 0)
                + float(post.get("comments", 0) or 0)
                + float(post.get("shares", 0) or 0)
            )
            for token in set(tokens):   # unique per post to avoid spam
                keyword_engagement[token] += engagement
                keyword_count[token] += 1

        # score = avg engagement per mention
        scored = [
            {
                "keyword": kw,
                "mentions": keyword_count[kw],
                "total_engagement": round(keyword_engagement[kw], 2),
                "avg_engagement_per_mention": round(
                    keyword_engagement[kw] / keyword_count[kw], 2
                ),
            }
            for kw in keyword_count
            if keyword_count[kw] >= 2   # at least 2 posts
        ]

        return sorted(scored, key=lambda x: x["avg_engagement_per_mention"], reverse=True)[:top_n]

    @staticmethod
    def _high_performing_formats(posts: list[dict]) -> list[dict[str, Any]]:
        """
        Groups posts by 'format' field (if present) or infers format from text signals,
        then ranks by average engagement.
        """
        from collections import defaultdict

        format_stats: dict[str, list[float]] = defaultdict(list)

        for post in posts:
            fmt = post.get("format") or _infer_format(post.get("text", ""))
            engagement = (
                float(post.get("likes", 0) or 0)
                + float(post.get("comments", 0) or 0)
                + float(post.get("shares", 0) or 0)
            )
            format_stats[fmt].append(engagement)

        results = [
            {
                "format": fmt,
                "post_count": len(vals),
                "avg_engagement": round(sum(vals) / len(vals), 2),
                "total_engagement": round(sum(vals), 2),
            }
            for fmt, vals in format_stats.items()
        ]

        return sorted(results, key=lambda x: x["avg_engagement"], reverse=True)


# ── module-level helper ───────────────────────────────────────────────────────

def _infer_format(text: str) -> str:
    """Infer post format from text signals when no explicit format is provided."""
    t = text.lower()
    if re.search(r"\b(watch|video|reel|youtube|clip)\b", t):
        return "video"
    if re.search(r"\b(photo|image|pic|picture|gallery)\b", t):
        return "image"
    if re.search(r"\b(thread|🧵)\b", t):
        return "thread"
    if re.search(r"\b(poll|vote|option)\b", t):
        return "poll"
    if re.search(r"\b(link|article|read|blog|post)\b", t):
        return "link"
    if len(text) > 280:
        return "long-form"
    return "short-text"


import re  # noqa: E402  (needed by _infer_format at module level)
