"""Tests for utils/nlp_utils.py"""
import pytest
from utils.nlp_utils import (
    clean_text,
    tokenize_words,
    avg_sentence_length,
    detect_tone,
    extract_keywords,
    engagement_summary,
    posting_frequency,
)


class TestCleanText:
    def test_lowercases(self):
        assert clean_text("Hello World") == "hello world"

    def test_strips_urls(self):
        result = clean_text("Check https://example.com for more")
        assert "https" not in result
        assert "example.com" not in result

    def test_strips_mentions(self):
        result = clean_text("Hello @user how are you")
        assert "@user" not in result

    def test_keeps_hashtag_word(self):
        result = clean_text("Love #marketing today")
        assert "marketing" in result
        assert "#" not in result

    def test_collapses_whitespace(self):
        result = clean_text("too   many    spaces")
        assert "  " not in result


class TestTokenizeWords:
    def test_returns_list_of_strings(self):
        tokens = tokenize_words("AI is transforming marketing")
        assert isinstance(tokens, list)
        assert all(isinstance(t, str) for t in tokens)

    def test_removes_stopwords_by_default(self):
        tokens = tokenize_words("the quick brown fox")
        assert "the" not in tokens

    def test_keeps_stopwords_when_disabled(self):
        tokens = tokenize_words("the quick brown fox", remove_stopwords=False)
        assert "the" in tokens

    def test_removes_punctuation(self):
        tokens = tokenize_words("hello, world!")
        assert "," not in tokens
        assert "!" not in tokens


class TestAvgSentenceLength:
    def test_single_sentence(self):
        result = avg_sentence_length("This is a test sentence.")
        assert result > 0

    def test_empty_string(self):
        assert avg_sentence_length("") == 0.0

    def test_multiple_sentences(self):
        text = "Short. This is a longer sentence with more words."
        result = avg_sentence_length(text)
        assert result > 0


class TestDetectTone:
    def test_promotional_tone(self):
        text = "Buy now! Limited time offer. Exclusive deal just for you."
        assert detect_tone(text) == "promotional"

    def test_casual_tone(self):
        text = "lol omg this is so wow haha yeah gonna do it tbh"
        assert detect_tone(text) == "casual"

    def test_returns_valid_tone(self):
        result = detect_tone("Some generic text about business strategy.")
        assert result in ("casual", "formal", "promotional", "informational")


class TestExtractKeywords:
    def test_returns_list(self):
        texts = ["AI marketing tools", "marketing automation software"]
        result = extract_keywords(texts)
        assert isinstance(result, list)

    def test_single_text_fallback(self):
        result = extract_keywords(["artificial intelligence marketing automation"])
        assert isinstance(result, list)

    def test_empty_texts_returns_empty(self):
        result = extract_keywords([])
        assert result == []

    def test_top_n_respected(self):
        texts = ["word1 word2 word3 word4 word5 word6", "word1 word2 word3 word4 word5 word6"]
        result = extract_keywords(texts, top_n=3)
        assert len(result) <= 3

    def test_filters_stopwords(self):
        texts = [
            "the quick brown fox jumps over the lazy dog",
            "the quick brown fox jumps over the lazy dog",
        ]
        result = extract_keywords(texts, top_n=10)
        stopwords_in_result = [t for t in result if t.lower() in {"the", "over", "and", "is"}]
        assert stopwords_in_result == []

    def test_filters_low_meaning_words(self):
        texts = [
            "using good things to make great stuff every day",
            "using good things to make great stuff every day",
        ]
        result = extract_keywords(texts, top_n=10)
        low_meaning = {"good", "great", "things", "using", "make", "every", "day"}
        for topic in result:
            for word in topic.lower().split():
                assert word not in low_meaning, f"Low-meaning word '{word}' found in topic '{topic}'"

    def test_prefers_bigrams_and_trigrams(self):
        texts = [
            "multi-agent systems are great for RAG pipelines and AI productivity tools",
            "multi-agent systems power RAG pipelines and AI productivity tools effectively",
            "building multi-agent systems with RAG pipelines improves AI productivity tools",
            "multi-agent systems combined with RAG pipelines drive AI productivity tools",
        ]
        result = extract_keywords(texts, top_n=10)
        # At least some results should be multi-word
        multi_word = [t for t in result if len(t.split()) > 1]
        assert len(multi_word) >= 2, f"Expected multi-word topics, got: {result}"

    def test_acronyms_uppercased(self):
        texts = [
            "RAG pipelines are used in AI systems for retrieval",
            "RAG pipelines improve AI systems with better retrieval",
            "building RAG pipelines for AI systems requires retrieval",
            "RAG pipelines power AI systems through retrieval augmentation",
        ]
        result = extract_keywords(texts, top_n=10)
        combined = " ".join(result)
        # RAG and AI should appear uppercased
        assert "RAG" in combined or "AI" in combined, f"Expected uppercase acronyms in: {result}"

    def test_minimum_frequency_filters_rare_terms(self):
        # With 4+ docs, min_freq=2 — a term appearing only once should be deprioritised
        texts = [
            "machine learning pipelines are powerful",
            "machine learning pipelines scale well",
            "machine learning pipelines need data",
            "machine learning pipelines require tuning",
            "completely unrelated obscure xyzterm appears once",
        ]
        result = extract_keywords(texts, top_n=5)
        assert "xyzterm" not in " ".join(result)


class TestEngagementSummary:
    def test_returns_expected_keys(self, sample_posts):
        result = engagement_summary(sample_posts)
        for key in ("total_posts", "avg_likes", "avg_engagement_rate", "top_post"):
            assert key in result

    def test_empty_posts_returns_empty(self):
        assert engagement_summary([]) == {}

    def test_totals_are_correct(self):
        posts = [
            {"likes": 10, "comments": 5, "shares": 2, "views": 100},
            {"likes": 20, "comments": 10, "shares": 4, "views": 200},
        ]
        result = engagement_summary(posts)
        assert result["total_likes"] == 30
        assert result["total_comments"] == 15

    def test_avg_engagement_rate_between_0_and_100(self, sample_posts):
        result = engagement_summary(sample_posts)
        assert 0 <= result["avg_engagement_rate"] <= 100


class TestPostingFrequency:
    def test_returns_expected_keys(self, sample_posts):
        result = posting_frequency(sample_posts)
        for key in ("total_posts", "posts_per_day", "peak_hour_utc", "peak_weekday"):
            assert key in result

    def test_no_timestamps_returns_note(self):
        posts = [{"text": "no timestamp here"}]
        result = posting_frequency(posts)
        assert "note" in result

    def test_posts_per_day_positive(self, sample_posts):
        result = posting_frequency(sample_posts)
        assert result["posts_per_day"] > 0
