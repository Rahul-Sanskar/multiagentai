"""
Copy Agent
----------
Generates post copy using the LLM when available, falling back to
template-based generation when OPENAI_API_KEY is not set or the call fails.

LLM path  : chat_completion() with a structured prompt
Fallback   : deterministic template engine (original behaviour)
"""
from __future__ import annotations

import json
import random
from typing import Any

from agents.base_agent import BaseAgent
from agents.content_context import ContentContext

# ── Platform word-count targets ───────────────────────────────────────────────

_PLATFORM_LENGTH: dict[str, int] = {
    "Instagram": 60,
    "LinkedIn":  150,
    "Twitter/X": 30,
    "TikTok":    50,
    "YouTube":   100,
}

# ── Fallback templates (used when LLM is unavailable) ────────────────────────

_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "casual": {
        "openers":    ["Okay, let's talk about {topic} 👀",
                       "Hot take: {topic} is changing everything 🔥",
                       "Can we just appreciate {topic} for a second?"],
        "connectors": ["Here's the thing —", "And honestly?", "The real deal:"],
        "ctas":       ["Drop a comment below 👇", "Tag someone who needs this!",
                       "Save this for later 🔖"],
    },
    "formal": {
        "openers":    ["Understanding {topic} is essential for today's professionals.",
                       "A closer look at {topic} reveals key insights.",
                       "{topic} continues to shape industry standards."],
        "connectors": ["Furthermore,", "It is worth noting that", "Research indicates"],
        "ctas":       ["Share your perspective in the comments.",
                       "Connect with us to learn more.",
                       "Follow for more industry insights."],
    },
    "promotional": {
        "openers":    ["Introducing the future of {topic} 🚀",
                       "Transform your results with {topic} — starting today.",
                       "Don't miss out on {topic}. Here's why it matters."],
        "connectors": ["The best part?", "What makes this special:", "Here's what you get:"],
        "ctas":       ["Click the link in bio to get started!",
                       "Limited time — act now! 🎯",
                       "DM us for exclusive access."],
    },
    "informational": {
        "openers":    ["Here's what you need to know about {topic}.",
                       "{topic} explained in plain terms.",
                       "A quick guide to {topic}:"],
        "connectors": ["Key point:", "Worth knowing:", "The takeaway:"],
        "ctas":       ["Found this helpful? Share it! ♻️",
                       "Follow for more tips like this.",
                       "Bookmark this post for reference 📌"],
    },
    "inspirational": {
        "openers":    ["Your journey with {topic} starts with one step. 💪",
                       "{topic} isn't just a skill — it's a mindset.",
                       "The people who master {topic} all started where you are now."],
        "connectors": ["Remember:", "The secret is simple:", "What separates the best:"],
        "ctas":       ["You've got this. Share if this resonated 🙌",
                       "Tag someone who needs to hear this today.",
                       "Follow for your daily dose of motivation."],
    },
}
_DEFAULT_TONE = "informational"


class CopyAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="CopyAgent")

    # ── Agent protocol ────────────────────────────────────────────────────

    async def run(self, task: str, context: dict | None = None) -> str:
        ctx = ContentContext.from_dict(context or {})
        result = await self.generate(ctx)
        return json.dumps(result)

    # ── Core (async, reusable) ────────────────────────────────────────────

    async def generate(self, ctx: ContentContext) -> dict[str, Any]:
        post_text, source = await self._generate(ctx)
        self.logger.info("copy_generated", topic=ctx.topic, tone=ctx.tone,
                         platform=ctx.platform, source=source)
        return {
            "post":       post_text,
            "tone":       ctx.tone,
            "platform":   ctx.platform,
            "word_count": len(post_text.split()),
            "source":     source,   # "llm" | "template"
        }

    # ── LLM generation ────────────────────────────────────────────────────

    async def _generate(self, ctx: ContentContext) -> tuple[str, str]:
        """Try LLM first; fall back to template on any failure."""
        from services.llm_service import chat_completion, is_available, LLMError

        if is_available():
            try:
                text = await chat_completion(
                    messages=self._build_messages(ctx),
                    temperature=0.8,
                    max_tokens=300,
                )
                return text, "llm"
            except LLMError as exc:
                self.logger.warning("copy_llm_fallback", error=str(exc))

        return self._template_generate(ctx), "template"

    def _build_messages(self, ctx: ContentContext) -> list[dict]:
        word_target = _PLATFORM_LENGTH.get(ctx.platform, 80)
        kw_line = f"Keywords to weave in naturally: {', '.join(ctx.keywords[:6])}." if ctx.keywords else ""
        audience_line = f"Target audience: {ctx.audience}." if ctx.audience != "general" else ""
        brand_line = f"Brand voice: {ctx.brand_voice}." if ctx.brand_voice else ""

        # RAG grounding — inject retrieved context chunks so the LLM stays
        # anchored to real data from the profile/competitor reports.
        rag_section = ""
        if ctx.rag_chunks:
            formatted = "\n".join(f"- {c.strip()}" for c in ctx.rag_chunks[:4] if c.strip())
            rag_section = (
                f"\nUse the following context to ground your post in real insights "
                f"(do not copy verbatim — synthesise naturally):\n{formatted}\n"
            )

        system = (
            "You are an expert social media copywriter. "
            "Write posts that feel authentic, not AI-generated. "
            "Never use filler phrases like 'In today's world' or 'In conclusion'. "
            "Output only the post text — no labels, no explanations."
        )
        user = (
            f"Write a high-quality {ctx.platform} post in a {ctx.tone} tone about {ctx.topic}.\n"
            f"Use these keywords: {', '.join(ctx.keywords[:6]) if ctx.keywords else 'none'}.\n"
            f"Keep it engaging and natural.\n"
            f"{audience_line}\n"
            f"{brand_line}\n"
            f"{rag_section}\n"
            f"Target length: ~{word_target} words.\n"
            f"Include a natural call-to-action at the end."
        ).strip()

        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]

    # ── Template fallback ─────────────────────────────────────────────────

    def _template_generate(self, ctx: ContentContext) -> str:
        tone = ctx.tone if ctx.tone in _TEMPLATES else _DEFAULT_TONE
        tmpl = _TEMPLATES[tone]
        target_words = _PLATFORM_LENGTH.get(ctx.platform, 60)

        opener    = random.choice(tmpl["openers"]).format(topic=ctx.topic)
        connector = random.choice(tmpl["connectors"])
        cta       = random.choice(tmpl["ctas"])

        kw_phrase     = f" Key areas: {', '.join(ctx.keywords[:3])}." if ctx.keywords else ""
        audience_hint = f" Especially for {ctx.audience}." if ctx.audience != "general" else ""
        brand         = f" {ctx.brand_voice.strip()}." if ctx.brand_voice else ""

        body = f"{connector}{kw_phrase}{audience_hint}{brand}"
        post = f"{opener}\n\n{body.strip()}\n\n{cta}"

        words = post.split()
        if len(words) > target_words * 1.5:
            post = " ".join(words[: int(target_words * 1.5)])

        return post.strip()
