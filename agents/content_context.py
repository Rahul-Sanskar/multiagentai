"""
Shared context object passed to all content-creation agents.
Keeps the contract explicit and avoids loose dict key errors.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContentContext:
    # Required
    topic: str
    tone: str                          # casual | formal | promotional | informational | inspirational

    # Optional enrichment from earlier pipeline stages
    platform: str = "Instagram"        # target platform influences copy length / style
    audience: str = "general"          # e.g. "startup founders", "fitness enthusiasts"
    keywords: list[str] = field(default_factory=list)   # from ProfileIntelligenceAgent
    brand_voice: str = ""              # extra style hint, e.g. "witty and bold"
    example_posts: list[str] = field(default_factory=list)  # few-shot style examples
    rag_chunks: list[str] = field(default_factory=list)     # retrieved context from RAG
    extra: dict[str, Any] = field(default_factory=dict)     # catch-all for future fields

    # ── Helpers ───────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "tone": self.tone,
            "platform": self.platform,
            "audience": self.audience,
            "keywords": self.keywords,
            "brand_voice": self.brand_voice,
            "example_posts": self.example_posts,
            "rag_chunks": self.rag_chunks,
            **self.extra,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ContentContext":
        known = {k for k in cls.__dataclass_fields__}
        extra = {k: v for k, v in d.items() if k not in known}
        base  = {k: v for k, v in d.items() if k in known}
        return cls(**base, extra=extra)
