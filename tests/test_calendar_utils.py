"""Tests for utils/calendar_utils.py"""
import pytest
from datetime import date
from utils.calendar_utils import (
    build_topic_pool,
    generate_slots,
    parse_feedback,
    apply_patch,
    best_format_for_platform,
)


class TestBuildTopicPool:
    def test_returns_list_of_dicts(self, sample_profile_report, sample_competitor_report):
        pool = build_topic_pool(sample_profile_report, sample_competitor_report)
        assert isinstance(pool, list)
        for item in pool:
            assert "topic" in item
            assert "source" in item
            assert "priority" in item

    def test_no_duplicates(self, sample_profile_report, sample_competitor_report):
        pool = build_topic_pool(sample_profile_report, sample_competitor_report)
        topics = [p["topic"].lower() for p in pool]
        assert len(topics) == len(set(topics))

    def test_empty_reports_returns_empty(self):
        pool = build_topic_pool({}, {})
        assert pool == []


class TestGenerateSlots:
    def test_correct_number_of_slots(self, sample_profile_report):
        slots = generate_slots(date(2024, 2, 1), 14, sample_profile_report)
        assert len(slots) == 14

    def test_slots_have_required_fields(self, sample_profile_report):
        slots = generate_slots(date(2024, 2, 1), 5, sample_profile_report)
        for slot in slots:
            for field in ("day", "date", "platform", "format", "time", "locked"):
                assert field in slot

    def test_days_are_sequential(self, sample_profile_report):
        slots = generate_slots(date(2024, 2, 1), 5, sample_profile_report)
        days = [s["day"] for s in slots]
        assert days == list(range(1, 6))

    def test_all_slots_unlocked_by_default(self, sample_profile_report):
        slots = generate_slots(date(2024, 2, 1), 5, sample_profile_report)
        assert all(not s["locked"] for s in slots)

    def test_platforms_rotate(self, sample_profile_report):
        slots = generate_slots(date(2024, 2, 1), 10, sample_profile_report)
        platforms = [s["platform"] for s in slots]
        # Should have more than one unique platform
        assert len(set(platforms)) > 1


class TestParseFeedback:
    def test_parses_day_number(self):
        result = parse_feedback("Replace day 3 with AI agents topic")
        assert 3 in result["days"]

    def test_parses_topic(self):
        result = parse_feedback("Replace day 3 with AI agents topic")
        assert result["topic"] is not None
        assert "ai agents" in result["topic"].lower()

    def test_parses_platform(self):
        result = parse_feedback("Change day 7 to LinkedIn")
        assert result["platform"] == "LinkedIn"

    def test_parses_lock(self):
        result = parse_feedback("Lock day 5")
        assert result["lock"] is True

    def test_parses_unlock(self):
        result = parse_feedback("Unlock day 5")
        assert result["lock"] is False

    def test_parses_format(self):
        result = parse_feedback("Change day 2 to use a reel format")
        assert result["format"] is not None

    def test_no_day_returns_empty_list(self):
        result = parse_feedback("Change all topics to AI")
        assert result["days"] == []


class TestApplyPatch:
    def _entry(self, **kwargs):
        base = {
            "day": 1, "date": "2024-02-01", "platform": "Instagram",
            "format": "Reel", "time": "18:00", "topic": "old topic",
            "source": "profile", "priority": "medium", "locked": False,
        }
        base.update(kwargs)
        return base

    def test_updates_topic(self):
        entry = self._entry()
        patch = {"topic": "new topic", "platform": None, "format": None,
                 "time": None, "lock": None}
        result = apply_patch(entry, patch)
        assert result["topic"] == "new topic"
        assert result["source"] == "user_feedback"

    def test_locked_entry_not_modified(self):
        entry = self._entry(locked=True)
        patch = {"topic": "new topic", "platform": None, "format": None,
                 "time": None, "lock": None}
        result = apply_patch(entry, patch)
        assert result["topic"] == "old topic"

    def test_lock_patch_locks_entry(self):
        entry = self._entry()
        patch = {"topic": None, "platform": None, "format": None,
                 "time": None, "lock": True}
        result = apply_patch(entry, patch)
        assert result["locked"] is True

    def test_unlock_patch_unlocks_entry(self):
        entry = self._entry(locked=True)
        patch = {"topic": "new topic", "platform": None, "format": None,
                 "time": None, "lock": False}
        result = apply_patch(entry, patch)
        assert result["locked"] is False

    def test_does_not_mutate_original(self):
        entry = self._entry()
        original_topic = entry["topic"]
        patch = {"topic": "changed", "platform": None, "format": None,
                 "time": None, "lock": None}
        apply_patch(entry, patch)
        assert entry["topic"] == original_topic
