"""
Calendar utility functions — all pure, no side effects.
"""
from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

# ── Constants ─────────────────────────────────────────────────────────────────

PLATFORMS = ["Instagram", "LinkedIn", "Twitter/X", "YouTube", "TikTok"]

FORMATS = {
    "Instagram": ["Reel", "Carousel", "Story", "Static Image"],
    "LinkedIn":  ["Article", "Poll", "Short Post", "Document"],
    "Twitter/X": ["Thread", "Short Post", "Poll"],
    "YouTube":   ["Long-form Video", "Short", "Community Post"],
    "TikTok":    ["Short Video", "Duet", "Stitch"],
}

# Best posting times per platform (hour, UTC)
PEAK_TIMES = {
    "Instagram": "18:00",
    "LinkedIn":  "09:00",
    "Twitter/X": "12:00",
    "YouTube":   "15:00",
    "TikTok":    "19:00",
}

# ── Topic pool ────────────────────────────────────────────────────────────────

def build_topic_pool(
    profile_report: dict[str, Any],
    competitor_report: dict[str, Any],
) -> list[dict[str, str]]:
    """
    Merge profile keywords, competitor trending topics, and content gaps
    into a ranked topic pool.  Each entry: {topic, source, priority}.
    """
    pool: list[dict[str, str]] = []

    # 1. Profile's own top keywords (owned territory)
    for kw in profile_report.get("topics", {}).get("top_keywords", []):
        pool.append({"topic": kw, "source": "profile", "priority": "medium"})

    # 2. Trending competitor topics (high engagement signal)
    for item in competitor_report.get("trending_topics", []):
        kw = item.get("keyword", "")
        if kw:
            pool.append({"topic": kw, "source": "competitor_trending", "priority": "high"})

    # 3. Content gaps (untapped opportunity)
    for kw in competitor_report.get("content_gaps", {}).get("gaps", []):
        pool.append({"topic": kw, "source": "content_gap", "priority": "high"})

    # Deduplicate by topic text, keeping first occurrence
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for item in pool:
        key = item["topic"].lower().strip()
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


# ── Platform / format selection ───────────────────────────────────────────────

def best_format_for_platform(platform: str, tone: str) -> str:
    """Pick a format that fits the platform and detected tone."""
    options = FORMATS.get(platform, ["Short Post"])
    tone_map = {
        "promotional":   0,   # first option tends to be most visual/engaging
        "casual":        -1,  # last option tends to be lightest
        "formal":        1,
        "informational": 1,
    }
    idx = tone_map.get(tone, 0) % len(options)
    return options[idx]


def infer_platform_from_report(profile_report: dict[str, Any]) -> str:
    """
    Try to read platform from the report; fall back to LinkedIn as a safe default.
    """
    freq = profile_report.get("posting_frequency", {})
    # If the report carries a platform hint, use it
    platform = freq.get("platform") or profile_report.get("platform")
    if platform and platform in PLATFORMS:
        return platform
    return "LinkedIn"


# ── Slot generation ───────────────────────────────────────────────────────────

def generate_slots(
    start_date: date,
    days: int,
    profile_report: dict[str, Any],
) -> list[dict[str, Any]]:
    """
    Generate `days` calendar slots starting from `start_date`.
    Rotates platforms and respects peak posting times.
    """
    freq = profile_report.get("posting_frequency", {})
    peak_hour = freq.get("peak_hour_utc", 9)
    tone = profile_report.get("writing_style", {}).get("tone", "informational")

    slots = []
    for i in range(days):
        platform = PLATFORMS[i % len(PLATFORMS)]
        post_time = PEAK_TIMES.get(platform, f"{peak_hour:02d}:00")
        slots.append({
            "day": i + 1,
            "date": (start_date + timedelta(days=i)).isoformat(),
            "platform": platform,
            "format": best_format_for_platform(platform, tone),
            "time": post_time,
            "topic": None,          # filled by the agent
            "source": None,
            "priority": None,
            "locked": False,        # HITL: locked entries are never auto-updated
        })
    return slots


# ── Feedback parsing ──────────────────────────────────────────────────────────

# Patterns the feedback parser recognises
_DAY_PATTERNS = [
    r"\bday\s*(\d+)\b",                          # "day 3", "Day3"
    r"\bentry\s*(\d+)\b",                        # "entry 5"
    r"\b(\d+)(st|nd|rd|th)\s*(day|entry|post)\b",# "3rd day"
]

_TOPIC_PATTERNS = [
    r'(?:replace|change|update|set|use|make it about|switch to)\s+(?:with\s+)?["\']?(.+?)["\']?\s*(?:topic|content|post|$)',
    r'(?:topic|about|on)\s*[:\-]?\s*["\']?(.+?)["\']?\s*$',
    r'["\'](.+?)["\']',                          # quoted string fallback
]

_LOCK_PATTERNS = [r"\block\b", r"\bfreeze\b", r"\bkeep\b", r"\bdon.t change\b"]
_UNLOCK_PATTERNS = [r"\bunlock\b", r"\bunfreeze\b", r"\ballow changes\b"]
_PLATFORM_PATTERN = r"\b(instagram|linkedin|twitter|tiktok|youtube)\b"
_FORMAT_PATTERN   = r"\b(reel|carousel|story|article|thread|poll|video|short|post)\b"
_TIME_PATTERN     = r"\b(\d{1,2}:\d{2})\b"


def parse_feedback(feedback: str) -> dict[str, Any]:
    """
    Parse a natural-language feedback string into a structured patch dict.

    Returns
    -------
    {
        "days":     [3, 7],          # which days to update (empty = all)
        "topic":    "AI agents",     # new topic (None = no change)
        "platform": "LinkedIn",      # new platform (None = no change)
        "format":   "Article",       # new format (None = no change)
        "time":     "09:00",         # new time (None = no change)
        "lock":     True/False/None, # lock state change
    }
    """
    text = feedback.strip()
    lower = text.lower()

    # ── days ──────────────────────────────────────────────────────────────
    days: list[int] = []
    for pat in _DAY_PATTERNS:
        for m in re.finditer(pat, lower):
            days.append(int(m.group(1)))
    days = sorted(set(days))

    # ── topic ─────────────────────────────────────────────────────────────
    topic: str | None = None
    for pat in _TOPIC_PATTERNS:
        m = re.search(pat, lower)
        if m:
            candidate = m.group(1).strip().strip("'\"")
            if len(candidate) > 1:
                topic = candidate
                break

    # ── platform ──────────────────────────────────────────────────────────
    platform: str | None = None
    m = re.search(_PLATFORM_PATTERN, lower)
    if m:
        raw = m.group(1)
        platform = {"twitter": "Twitter/X", "linkedin": "LinkedIn",
                    "instagram": "Instagram", "tiktok": "TikTok",
                    "youtube": "YouTube"}.get(raw, raw.capitalize())

    # ── format ────────────────────────────────────────────────────────────
    fmt: str | None = None
    m = re.search(_FORMAT_PATTERN, lower)
    if m:
        fmt = m.group(1).capitalize()

    # ── time ──────────────────────────────────────────────────────────────
    time_val: str | None = None
    m = re.search(_TIME_PATTERN, lower)
    if m:
        time_val = m.group(1)

    # ── lock / unlock ─────────────────────────────────────────────────────
    lock: bool | None = None
    if any(re.search(p, lower) for p in _LOCK_PATTERNS):
        lock = True
    if any(re.search(p, lower) for p in _UNLOCK_PATTERNS):
        lock = False

    return {
        "days": days,
        "topic": topic,
        "platform": platform,
        "format": fmt,
        "time": time_val,
        "lock": lock,
    }


def apply_patch(entry: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """
    Apply a parsed feedback patch to a single calendar entry.
    Locked entries are never modified (unless the patch itself unlocks them).
    Returns a new dict (does not mutate the original).
    """
    updated = dict(entry)

    # Handle lock toggle first
    if patch.get("lock") is True:
        updated["locked"] = True
        return updated          # lock only, no other changes
    if patch.get("lock") is False:
        updated["locked"] = False

    # Respect locked state
    if updated.get("locked"):
        return updated

    if patch.get("topic"):
        updated["topic"] = patch["topic"]
        updated["source"] = "user_feedback"
        updated["priority"] = "user"
    if patch.get("platform"):
        updated["platform"] = patch["platform"]
    if patch.get("format"):
        updated["format"] = patch["format"]
    if patch.get("time"):
        updated["time"] = patch["time"]

    return updated
