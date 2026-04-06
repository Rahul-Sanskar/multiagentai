"""
Profile Intelligence Agent
--------------------------
Input : list of post dicts  →  { text, timestamp?, likes?, comments?, shares?, views? }
Output: structured JSON report covering writing style, topics, frequency, engagement.
"""
from typing import Any

from agents.base_agent import BaseAgent
from utils.nlp_utils import (
    writing_style,
    topic_clusters,
    posting_frequency,
    engagement_summary,
)


class ProfileIntelligenceAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="ProfileIntelligenceAgent")

    # ── public entry point ────────────────────────────────────────────────

    async def run(self, task: str, context: dict | None = None) -> str:
        """
        `context` must contain a 'posts' key with a list of post dicts.
        Returns a JSON string of the profile report.
        """
        import json
        posts = (context or {}).get("posts", [])
        report = self.analyze(posts)
        return json.dumps(report, indent=2, default=str)

    # ── core analysis (sync, reusable) ───────────────────────────────────

    def analyze(self, posts: list[dict]) -> dict[str, Any]:
        """
        Accepts a list of post dicts and returns a full profile report.
        Can be called directly without going through the agent dispatcher.
        """
        if not posts:
            self.logger.warning("no_posts_provided")
            return {"error": "No posts provided"}

        self.logger.info("analyzing_profile", post_count=len(posts))

        report = {
            "post_count": len(posts),
            "writing_style": writing_style(posts),
            "topics": topic_clusters(posts, top_n=15),
            "posting_frequency": posting_frequency(posts),
            "engagement": engagement_summary(posts),
        }

        self.logger.info("profile_analysis_complete")
        return report
