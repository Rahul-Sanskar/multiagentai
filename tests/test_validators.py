"""Tests for utils/validators.py"""
import pytest
from utils.validators import (
    validate_posts,
    validate_platform,
    validate_tone,
    validate_topic,
    validate_iso_date,
    validate_review_status,
    validate_keywords,
    validate_days,
)
from utils.exceptions import EmptyInputError, InvalidFieldError, ValidationError


class TestValidatePosts:
    def test_valid_posts(self):
        posts = [{"text": "Hello world", "likes": 10}]
        validate_posts(posts)  # should not raise

    def test_empty_list_raises(self):
        with pytest.raises(EmptyInputError):
            validate_posts([])

    def test_missing_text_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_posts([{"likes": 5}])

    def test_empty_text_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_posts([{"text": "   "}])

    def test_text_too_long_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_posts([{"text": "x" * 5001}])

    def test_negative_metric_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_posts([{"text": "hi", "likes": -1}])

    def test_too_many_posts_raises(self):
        posts = [{"text": "post"} for _ in range(501)]
        with pytest.raises(ValidationError):
            validate_posts(posts)


class TestValidatePlatform:
    def test_valid_platforms(self):
        assert validate_platform("Instagram") == "Instagram"
        assert validate_platform("linkedin") == "LinkedIn"
        assert validate_platform("twitter") == "Twitter/X"
        assert validate_platform("Twitter/X") == "Twitter/X"
        assert validate_platform("tiktok") == "TikTok"
        assert validate_platform("youtube") == "YouTube"

    def test_invalid_platform_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_platform("Snapchat")


class TestValidateTone:
    def test_valid_tones(self):
        for tone in ("casual", "formal", "promotional", "informational", "inspirational"):
            assert validate_tone(tone) == tone

    def test_invalid_tone_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_tone("aggressive")

    def test_case_insensitive(self):
        assert validate_tone("CASUAL") == "casual"


class TestValidateTopic:
    def test_valid_topic(self):
        assert validate_topic("AI marketing") == "AI marketing"

    def test_too_short_raises(self):
        with pytest.raises(EmptyInputError):
            validate_topic("x")

    def test_too_long_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_topic("x" * 201)

    def test_strips_whitespace(self):
        assert validate_topic("  hello  ") == "hello"


class TestValidateIsoDate:
    def test_valid_date(self):
        assert validate_iso_date("2024-02-01") == "2024-02-01"

    def test_invalid_date_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_iso_date("not-a-date")


class TestValidateReviewStatus:
    def test_valid_statuses(self):
        for s in ("pending", "approved", "revision"):
            assert validate_review_status(s) == s

    def test_invalid_status_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_review_status("rejected")


class TestValidateKeywords:
    def test_valid_keywords(self):
        result = validate_keywords(["ai", "marketing", "growth"])
        assert result == ["ai", "marketing", "growth"]

    def test_strips_empty_strings(self):
        result = validate_keywords(["ai", "", "  "])
        assert result == ["ai"]

    def test_too_many_raises(self):
        with pytest.raises(ValidationError):
            validate_keywords(["kw"] * 21)

    def test_non_string_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_keywords([123])


class TestValidateDays:
    def test_valid_days(self):
        assert validate_days(14) == 14
        assert validate_days(1) == 1

    def test_too_low_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_days(0)

    def test_too_high_raises(self):
        with pytest.raises(InvalidFieldError):
            validate_days(31)
