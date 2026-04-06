"""
Content Creation Orchestrator
------------------------------
Fans out to CopyAgent, HashtagAgent, and VisualAgent in parallel,
then merges their outputs into a single structured result.

Output schema
-------------
{
    "post":           str,
    "hashtags":       list[str],
    "visual_prompt":  str,
    "negative_prompt": str,
    "metadata": {
        "tone":         str,
        "platform":     str,
        "word_count":   int,
        "hashtag_count": int,
        "aspect_ratio": str,
    }
}
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

from agents.copy_agent import CopyAgent
from agents.hashtag_agent import HashtagAgent
from agents.visual_agent import VisualAgent
from agents.content_context import ContentContext
from utils.logger import get_logger

logger = get_logger("ContentCreationOrchestrator")


class ContentCreationOrchestrator:

    def __init__(self):
        self._copy    = CopyAgent()
        self._hashtag = HashtagAgent()
        self._visual  = VisualAgent()

    # ── Main entry point ──────────────────────────────────────────────────

    async def create(self, ctx: ContentContext) -> dict[str, Any]:
        """
        Run all three agents concurrently and merge into one payload.
        """
        logger.info("content_creation_start", topic=ctx.topic, tone=ctx.tone, platform=ctx.platform)

        ctx_dict = ctx.to_dict()

        copy_task    = self._copy.run(ctx.topic, ctx_dict)
        hashtag_task = self._hashtag.run(ctx.topic, ctx_dict)
        visual_task  = self._visual.run(ctx.topic, ctx_dict)

        copy_raw, hashtag_raw, visual_raw = await asyncio.gather(
            copy_task, hashtag_task, visual_task
        )

        copy_out    = json.loads(copy_raw)
        hashtag_out = json.loads(hashtag_raw)
        visual_out  = json.loads(visual_raw)

        result = _merge(copy_out, hashtag_out, visual_out)
        logger.info("content_creation_complete", topic=ctx.topic)
        return result

    # ── Convenience: accept raw dict instead of ContentContext ────────────

    async def create_from_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        return await self.create(ContentContext.from_dict(data))

    # ── Batch: generate for multiple topics at once ───────────────────────

    async def create_batch(self, contexts: list[ContentContext]) -> list[dict[str, Any]]:
        return list(await asyncio.gather(*[self.create(ctx) for ctx in contexts]))


# ── Merge helper ──────────────────────────────────────────────────────────────

def _merge(
    copy_out: dict[str, Any],
    hashtag_out: dict[str, Any],
    visual_out: dict[str, Any],
) -> dict[str, Any]:
    return {
        "post":           copy_out["post"],
        "hashtags":       hashtag_out["hashtags"],
        "visual_prompt":  visual_out["visual_prompt"],
        "negative_prompt": visual_out.get("negative_prompt", ""),
        "metadata": {
            "tone":          copy_out.get("tone"),
            "platform":      copy_out.get("platform"),
            "word_count":    copy_out.get("word_count"),
            "hashtag_count": hashtag_out.get("count"),
            "aspect_ratio":  visual_out.get("aspect_ratio"),
        },
    }


# Singleton
content_creation_orchestrator = ContentCreationOrchestrator()
