"""
Visual Agent
------------
Generates a detailed image-generation prompt using the LLM when available,
falling back to a rule-based builder when the API is unavailable.

LLM path  : asks the model for a rich, specific Midjourney/DALL-E prompt
Fallback   : tone + platform style map (original behaviour)
"""
from __future__ import annotations

import json
from typing import Any

from agents.base_agent import BaseAgent
from agents.content_context import ContentContext

# ── Style reference maps (used by fallback + injected into LLM prompt) ───────

_TONE_STYLE: dict[str, dict[str, str]] = {
    "casual": {
        "mood":    "vibrant, fun, energetic",
        "palette": "bright saturated colors, playful gradients",
        "style":   "flat design illustration, bold outlines",
    },
    "formal": {
        "mood":    "clean, professional, authoritative",
        "palette": "navy blue, white, subtle gold accents",
        "style":   "minimalist corporate photography, sharp lines",
    },
    "promotional": {
        "mood":    "exciting, urgent, eye-catching",
        "palette": "high-contrast red and yellow, neon accents",
        "style":   "bold graphic design, product-focused composition",
    },
    "informational": {
        "mood":    "clear, trustworthy, educational",
        "palette": "soft blues and greens, neutral backgrounds",
        "style":   "infographic-style illustration, clean typography",
    },
    "inspirational": {
        "mood":    "uplifting, warm, aspirational",
        "palette": "golden hour tones, warm oranges and soft purples",
        "style":   "cinematic photography, wide-angle, dramatic lighting",
    },
}

_PLATFORM_SPEC: dict[str, dict[str, str]] = {
    "Instagram": {"ratio": "1:1 square or 4:5 portrait", "focus": "visually striking hero image"},
    "LinkedIn":  {"ratio": "1.91:1 landscape",           "focus": "professional scene or data visual"},
    "Twitter/X": {"ratio": "16:9 landscape",             "focus": "bold text overlay or simple graphic"},
    "TikTok":    {"ratio": "9:16 vertical",              "focus": "dynamic motion-ready scene"},
    "YouTube":   {"ratio": "16:9 landscape thumbnail",   "focus": "expressive face or bold title graphic"},
}

_QUALITY_SUFFIX = (
    "ultra-detailed, 4K resolution, professional photography, "
    "award-winning composition, sharp focus"
)


class VisualAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="VisualAgent")

    # ── Agent protocol ────────────────────────────────────────────────────

    async def run(self, task: str, context: dict | None = None) -> str:
        ctx = ContentContext.from_dict(context or {})
        result = await self.generate(ctx)
        return json.dumps(result)

    # ── Core (async, reusable) ────────────────────────────────────────────

    async def generate(self, ctx: ContentContext) -> dict[str, Any]:
        prompt, negative, source = await self._build_prompt(ctx)
        self.logger.info("visual_prompt_generated", topic=ctx.topic,
                         platform=ctx.platform, source=source)
        return {
            "visual_prompt":   prompt,
            "negative_prompt": negative,
            "platform":        ctx.platform,
            "aspect_ratio":    _PLATFORM_SPEC.get(ctx.platform, {}).get("ratio", "1:1"),
            "source":          source,
        }

    # ── LLM generation ────────────────────────────────────────────────────

    async def _build_prompt(self, ctx: ContentContext) -> tuple[str, str, str]:
        from services.llm_service import chat_completion, is_available, LLMError

        if is_available():
            try:
                raw = await chat_completion(
                    messages=self._build_messages(ctx),
                    temperature=0.9,
                    max_tokens=200,
                )
                prompt = raw.strip()
                if len(prompt) > 30:
                    negative = self._negative_prompt(ctx)
                    return prompt, negative, "llm"
                self.logger.warning("visual_llm_too_short", chars=len(prompt))
            except LLMError as exc:
                self.logger.warning("visual_llm_fallback", error=str(exc))

        return self._fallback_prompt(ctx), self._negative_prompt(ctx), "template"

    def _build_messages(self, ctx: ContentContext) -> list[dict]:
        tone_style   = _TONE_STYLE.get(ctx.tone, _TONE_STYLE["informational"])
        platform_spec = _PLATFORM_SPEC.get(ctx.platform, _PLATFORM_SPEC["Instagram"])
        kw_line = f"Visual themes to include: {', '.join(ctx.keywords[:4])}." if ctx.keywords else ""
        audience_line = f"The image should appeal to: {ctx.audience}." if ctx.audience != "general" else ""

        system = (
            "You are an expert AI image prompt engineer specialising in social media visuals. "
            "Write detailed, specific image generation prompts for Midjourney or DALL-E. "
            "Be concrete about subjects, lighting, composition, and style. "
            "Output ONLY the prompt text — no labels, no explanations."
        )
        user = (
            f"Create a detailed image generation prompt for a {ctx.platform} post about: {ctx.topic}.\n"
            f"Mood: {tone_style['mood']}.\n"
            f"Color palette: {tone_style['palette']}.\n"
            f"Visual style: {tone_style['style']}.\n"
            f"Composition: {platform_spec['focus']}, {platform_spec['ratio']} format.\n"
            f"{kw_line}\n"
            f"{audience_line}\n"
            f"End with: {_QUALITY_SUFFIX}."
        ).strip()

        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ]

    # ── Template fallback ─────────────────────────────────────────────────

    def _fallback_prompt(self, ctx: ContentContext) -> str:
        tone_style    = _TONE_STYLE.get(ctx.tone, _TONE_STYLE["informational"])
        platform_spec = _PLATFORM_SPEC.get(ctx.platform, _PLATFORM_SPEC["Instagram"])
        subject       = _subject_from_topic(ctx.topic)

        kw_detail      = f", incorporating themes of {', '.join(ctx.keywords[:3])}" if ctx.keywords else ""
        audience_detail = f", appealing to {ctx.audience}" if ctx.audience != "general" else ""

        return (
            f"{subject}{kw_detail}{audience_detail}. "
            f"Mood: {tone_style['mood']}. "
            f"Color palette: {tone_style['palette']}. "
            f"Visual style: {tone_style['style']}. "
            f"Composition: {platform_spec['focus']}, {platform_spec['ratio']} format. "
            f"{_QUALITY_SUFFIX}."
        ).strip()

    def _negative_prompt(self, ctx: ContentContext) -> str:
        base = "blurry, low quality, watermark, text overlay, distorted faces, oversaturated"
        if ctx.tone == "formal":
            base += ", cartoonish, childish, cluttered"
        elif ctx.tone == "casual":
            base += ", corporate, stiff, boring"
        return base


# ── Helpers ───────────────────────────────────────────────────────────────────

def _subject_from_topic(topic: str) -> str:
    topic = topic.strip().lower()
    visual_map = [
        (["ai", "machine learning", "neural", "deep learning", "llm", "langgraph"],
         "A futuristic digital brain with glowing neural network connections"),
        (["rag", "retrieval", "vector", "embedding"],
         "Abstract data streams flowing into a glowing knowledge core"),
        (["social media", "instagram", "tiktok", "content"],
         "A person creating content on a smartphone, surrounded by floating social media icons"),
        (["marketing", "growth", "brand"],
         "An upward-trending graph with vibrant marketing icons and a confident professional"),
        (["startup", "entrepreneur", "business"],
         "A dynamic entrepreneur at a modern workspace with city skyline in the background"),
        (["fitness", "health", "wellness"],
         "An energetic athlete in motion against a bright, motivating background"),
        (["finance", "investment", "money"],
         "Abstract financial charts and coins with a clean, professional aesthetic"),
        (["education", "learning", "course"],
         "An open book transforming into digital knowledge streams and light"),
        (["technology", "software", "code", "developer"],
         "A developer surrounded by holographic code and glowing screens"),
        (["community", "team", "collaboration"],
         "A diverse group of people collaborating in a bright, modern space"),
    ]
    for keywords, visual in visual_map:
        if any(kw in topic for kw in keywords):
            return visual
    return f"A compelling visual scene representing the concept of {topic}"
