"""
Reusable input validators shared across agents, services, and API layers.
All validators raise typed exceptions from utils.exceptions.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from utils.exceptions import EmptyInputError, InvalidFieldError, ValidationError

# ── Post validation ───────────────────────────────────────────────────────────

_MIN_POST_TEXT = 1
_MAX_POST_TEXT = 5000
_MAX_POSTS = 500

VALID_PLATFORMS = {"Instagram", "LinkedIn", "Twitter/X", "TikTok", "YouTube"}
VALID_TONES = {"casual", "formal", "promotional", "informational", "inspirational"}
VALID_REVIEW_STATUSES = {"pending", "approved", "revision"}


def validate_posts(posts: list[dict[str, Any]], field_name: str = "posts") -> None:
    """Validate a list of post dicts."""
    if not posts:
        raise EmptyInputError(f"'{field_name}' must contain at least one post.")
    if len(posts) > _MAX_POSTS:
        raise ValidationError(
            f"'{field_name}' exceeds maximum of {_MAX_POSTS} posts (got {len(posts)})."
        )
    for i, post in enumerate(posts):
        text = post.get("text", "")
        if not isinstance(text, str) or len(text.strip()) < _MIN_POST_TEXT:
            raise InvalidFieldError(
                f"Post at index {i} has empty or missing 'text'.",
                detail=f"{field_name}[{i}].text must be a non-empty string.",
            )
        if len(text) > _MAX_POST_TEXT:
            raise InvalidFieldError(
                f"Post at index {i} 'text' exceeds {_MAX_POST_TEXT} characters.",
                detail=f"{field_name}[{i}].text is too long.",
            )
        for metric in ("likes", "comments", "shares", "views"):
            val = post.get(metric)
            if val is not None and (not isinstance(val, (int, float)) or val < 0):
                raise InvalidFieldError(
                    f"Post at index {i} has invalid '{metric}': must be a non-negative number.",
                )


def validate_platform(platform: str) -> str:
    """Normalise and validate a platform name."""
    _map = {
        "twitter": "Twitter/X",
        "twitter/x": "Twitter/X",
        "x": "Twitter/X",
        "instagram": "Instagram",
        "linkedin": "LinkedIn",
        "tiktok": "TikTok",
        "youtube": "YouTube",
    }
    normalised = _map.get(platform.lower().strip(), platform)
    if normalised not in VALID_PLATFORMS:
        raise InvalidFieldError(
            f"Unknown platform '{platform}'. Valid: {sorted(VALID_PLATFORMS)}."
        )
    return normalised


def validate_tone(tone: str) -> str:
    """Validate and return a tone string."""
    t = tone.lower().strip()
    if t not in VALID_TONES:
        raise InvalidFieldError(
            f"Unknown tone '{tone}'. Valid: {sorted(VALID_TONES)}."
        )
    return t


def validate_topic(topic: str, field_name: str = "topic") -> str:
    """Validate a topic string."""
    t = topic.strip()
    if len(t) < 2:
        raise EmptyInputError(f"'{field_name}' must be at least 2 characters.")
    if len(t) > 200:
        raise InvalidFieldError(f"'{field_name}' must be 200 characters or fewer.")
    return t


def validate_iso_date(value: str, field_name: str = "date") -> str:
    """Validate an ISO date string (YYYY-MM-DD)."""
    try:
        datetime.fromisoformat(value)
        return value
    except ValueError:
        raise InvalidFieldError(
            f"'{field_name}' must be a valid ISO date string (YYYY-MM-DD), got '{value}'."
        )


def validate_review_status(status: str) -> str:
    """Validate a review status string."""
    s = status.lower().strip()
    if s not in VALID_REVIEW_STATUSES:
        raise InvalidFieldError(
            f"Invalid status '{status}'. Valid: {sorted(VALID_REVIEW_STATUSES)}."
        )
    return s


def validate_keywords(keywords: list[Any], max_count: int = 20) -> list[str]:
    """Validate and clean a list of keyword strings."""
    if not isinstance(keywords, list):
        raise InvalidFieldError("'keywords' must be a list.")
    if len(keywords) > max_count:
        raise ValidationError(f"'keywords' exceeds maximum of {max_count} items.")
    cleaned = []
    for i, kw in enumerate(keywords):
        if not isinstance(kw, str):
            raise InvalidFieldError(f"keywords[{i}] must be a string.")
        cleaned.append(kw.strip())
    return [k for k in cleaned if k]


def validate_days(days: int, min_days: int = 1, max_days: int = 30) -> int:
    """Validate a calendar days count."""
    if not isinstance(days, int) or days < min_days or days > max_days:
        raise InvalidFieldError(
            f"'days' must be an integer between {min_days} and {max_days}."
        )
    return days
