"""
Hashtag Agent
-------------
Generates platform-aware hashtags using the LLM when available,
falling back to a keyword-bank approach when the API is unavailable.

LLM path  : asks the model for 8–12 specific, non-generic hashtags
Fallback   : topic + keyword + tone bank (original behaviour)
"""
from __future__ import annotations

import json
import re
from typing import Any

from agents.base_agent import BaseAgent
from agents.content_context import ContentContext

# ── Platform count targets ────────────────────────────────────────────────────

_PLATFORM_COUNT: dict[str, int] = {
    "Instagram": 12,
    "LinkedIn":  5,
    "Twitter/X": 3,
    "TikTok":    10,
    "YouTube":   8,
}

# ── Fallback banks ────────────────────────────────────────────────────────────

_TONE_TAGS: dict[str, list[str]] = {
    "casual":        ["vibes", "trending", "fyp", "relatable", "mood"],
    "formal":        ["thoughtLeadership", "industry", "professional", "insights", "leadership"],
    "promotional":   ["sale", "offer", "limitedTime", "exclusive", "dealNow"],
    "informational": ["tips", "howTo", "learnMore", "didYouKnow", "education"],
    "inspirational": ["motivation", "mindset", "growthMindset", "inspiration", "success"],
}

_PLATFORM_TAGS: dict[str, list[str]] = {
    "Instagram": ["instagram", "instadaily", "explorepage", "reels"],
    "LinkedIn":  ["linkedin", "linkedinLearning", "networking", "career"],
    "Twitter/X": ["twitterX", "trending"],
    "TikTok":    ["tiktok", "tikTokViral", "foryoupage", "fyp"],
    "YouTube":   ["youtube", "youtubeVideos", "subscribe"],
}


class HashtagAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="HashtagAgent")

    # ── Agent protocol ────────────────────────────────────────────────────

    async def run(self, task: str, context: dict | None = None) -> str:
        ctx = ContentContext.from_dict(context or {})
        result = await self.generate(ctx)
        return json.dumps(result)

    # ── Core (async, reusable) ────────────────────────────────────────────

    async def generate(self, ctx: ContentContext) -> dict[str, Any]:
        hashtags, source = await self._build(ctx)
        self.logger.info("hashtags_generated", count=len(hashtags),
                         platform=ctx.platform, source=source)
        return {
            "hashtags": hashtags,
            "count":    len(hashtags),
            "platform": ctx.platform,
            "source":   source,
        }

    # ── LLM generation ────────────────────────────────────────────────────

    async def _build(self, ctx: ContentContext) -> tuple[list[str], str]:
        from services.llm_service import chat_completion, is_available, LLMError

        target = _PLATFORM_COUNT.get(ctx.platform, 10)

        if is_available():
            try:
                raw = await chat_completion(
                    messages=self._build_messages(ctx, target),
                    temperature=0.6,
                    max_tokens=150,
                )
                tags = _parse_llm_hashtags(raw, target)
                if tags:
                    return tags, "llm"
                self.logger.warning("hashtag_llm_parse_empty", raw=raw[:100])
            except LLMError as exc:
                self.logger.warning("hashtag_llm_fallback", error=str(exc))

        return self._fallback_build(ctx, target), "template"

    def _build_messages(self, ctx: ContentContext, target: int) -> list[dict]:
        kw_line = f"Related keywords: {', '.join(ctx.keywords[:8])}." if ctx.keywords else ""
        system = (
            "You are a social media hashtag strategist. "
            "Generate specific, niche hashtags that real audiences follow. "
            "Avoid generic tags like #love, #instagood, #follow, #like. "
            "Output ONLY a space-separated list of hashtags starting with #. "
            "No explanations, no numbering, no newlines between tags."
        )
        user = (
            f"Generate {target} relevant hashtags for a {ctx.platform} post "
            f"about: {ctx.topic}.\n"
            f"Tone: {ctx.tone}.\n"
            f"{kw_line}\n"
            f"Mix: 3 broad niche tags, {target - 6} specific topic tags, 3 community tags."
        ).strip()

        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]

    # ── Template fallback ─────────────────────────────────────────────────

    def _fallback_build(self, ctx: ContentContext, target: int) -> list[str]:
        pool: list[str] = []
        pool += _topic_to_tags(ctx.topic)
        for kw in ctx.keywords[:8]:
            pool += _topic_to_tags(kw)
        pool += _TONE_TAGS.get(ctx.tone, [])
        pool += _PLATFORM_TAGS.get(ctx.platform, [])

        seen: set[str] = set()
        result: list[str] = []
        for tag in pool:
            clean = _normalise(tag)
            if clean and clean not in seen:
                seen.add(clean)
                result.append(f"#{clean}")
            if len(result) >= target:
                break
        return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_llm_hashtags(raw: str, target: int) -> list[str]:
    """Extract #hashtag tokens from LLM output, normalise, deduplicate."""
    # Find all tokens that start with # or look like hashtags
    tokens = re.findall(r"#?\w+", raw)
    seen: set[str] = set()
    result: list[str] = []
    for token in tokens:
        tag = token.lstrip("#").strip()
        if len(tag) < 2:
            continue
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            result.append(f"#{tag}")
        if len(result) >= target:
            break
    return result


def _normalise(tag: str) -> str:
    tag = tag.strip().lower()
    tag = re.sub(r"[^\w\s]", "", tag)
    words = tag.split()
    if not words:
        return ""
    return words[0] + "".join(w.title() for w in words[1:])


def _topic_to_tags(topic: str) -> list[str]:
    tags = [topic.replace(" ", "")]
    for word in topic.split():
        if len(word) > 2:
            tags.append(word)
    return tags
