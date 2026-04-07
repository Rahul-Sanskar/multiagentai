"""
Profile Intelligence Agent
--------------------------
Input : list of post dicts  →  { text, timestamp?, likes?, comments?, shares?, views?, format? }
Output: structured JSON report covering writing style, topics, frequency, engagement,
        and content format distribution.
"""
from typing import Any

from agents.base_agent import BaseAgent
from utils.nlp_utils import (
    writing_style,
    topic_clusters,
    posting_frequency,
    engagement_summary,
    detect_content_format,
    format_distribution,
)


class ProfileIntelligenceAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="ProfileIntelligenceAgent")

    async def run(self, task: str, context: dict | None = None) -> str:
        import json
        posts = (context or {}).get("posts", [])
        report = self.analyze(posts)
        return json.dumps(report, indent=2, default=str)

    def analyze(self, posts: list[dict]) -> dict[str, Any]:
        """
        Accepts a list of post dicts and returns a full profile report
        including content format distribution and per-post format tags.
        """
        if not posts:
            self.logger.warning("no_posts_provided")
            return {"error": "No posts provided"}

        self.logger.info("analyzing_profile", post_count=len(posts))

        # Tag each post with its detected format
        tagged_posts = []
        for p in posts:
            tagged = dict(p)
            if not tagged.get("format"):
                tagged["format"] = detect_content_format(p.get("text", ""))
            tagged_posts.append(tagged)

        report = {
            "post_count":        len(tagged_posts),
            "writing_style":     writing_style(tagged_posts),
            "topics":            topic_clusters(tagged_posts, top_n=15),
            "posting_frequency": posting_frequency(tagged_posts),
            "engagement":        engagement_summary(tagged_posts),
            "format_distribution": format_distribution(tagged_posts),
        }

        self.logger.info("profile_analysis_complete")
        return report
        return report
