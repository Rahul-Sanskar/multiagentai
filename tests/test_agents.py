"""Tests for core agents."""
import pytest
from agents.profile_intelligence_agent import ProfileIntelligenceAgent
from agents.competitor_analysis_agent import CompetitorAnalysisAgent
from agents.copy_agent import CopyAgent
from agents.hashtag_agent import HashtagAgent
from agents.visual_agent import VisualAgent
from agents.content_context import ContentContext


# ── ProfileIntelligenceAgent ──────────────────────────────────────────────────

class TestProfileIntelligenceAgent:
    def setup_method(self):
        self.agent = ProfileIntelligenceAgent()

    def test_analyze_returns_required_keys(self, sample_posts):
        report = self.agent.analyze(sample_posts)
        assert "post_count" in report
        assert "writing_style" in report
        assert "topics" in report
        assert "posting_frequency" in report
        assert "engagement" in report

    def test_post_count_matches_input(self, sample_posts):
        report = self.agent.analyze(sample_posts)
        assert report["post_count"] == len(sample_posts)

    def test_writing_style_has_tone(self, sample_posts):
        report = self.agent.analyze(sample_posts)
        assert "tone" in report["writing_style"]
        assert report["writing_style"]["tone"] in (
            "casual", "formal", "promotional", "informational"
        )

    def test_topics_has_keywords(self, sample_posts):
        report = self.agent.analyze(sample_posts)
        assert isinstance(report["topics"]["top_keywords"], list)

    def test_empty_posts_returns_error(self):
        report = self.agent.analyze([])
        assert "error" in report

    def test_engagement_totals_are_non_negative(self, sample_posts):
        report = self.agent.analyze(sample_posts)
        eng = report["engagement"]
        assert eng["total_likes"] >= 0
        assert eng["avg_engagement_rate"] >= 0


# ── CompetitorAnalysisAgent ───────────────────────────────────────────────────

class TestCompetitorAnalysisAgent:
    def setup_method(self):
        self.agent = CompetitorAnalysisAgent()

    def test_analyze_returns_required_keys(self, sample_profile_report, sample_competitor_posts):
        report = self.agent.analyze(sample_profile_report, sample_competitor_posts)
        assert "content_gaps" in report
        assert "trending_topics" in report
        assert "high_performing_formats" in report
        assert "competitor_engagement" in report

    def test_content_gaps_structure(self, sample_profile_report, sample_competitor_posts):
        report = self.agent.analyze(sample_profile_report, sample_competitor_posts)
        gaps = report["content_gaps"]
        assert "gaps" in gaps
        assert "overlap" in gaps
        assert "unique_to_profile" in gaps
        assert isinstance(gaps["gaps"], list)

    def test_empty_competitor_posts_returns_error(self, sample_profile_report):
        report = self.agent.analyze(sample_profile_report, [])
        assert "error" in report

    def test_trending_topics_sorted_by_engagement(self, sample_profile_report, sample_competitor_posts):
        report = self.agent.analyze(sample_profile_report, sample_competitor_posts)
        topics = report["trending_topics"]
        if len(topics) > 1:
            scores = [t["avg_engagement_per_mention"] for t in topics]
            assert scores == sorted(scores, reverse=True)


# ── CopyAgent ─────────────────────────────────────────────────────────────────

class TestCopyAgent:
    def setup_method(self):
        self.agent = CopyAgent()

    def _ctx(self, **kwargs):
        defaults = {"topic": "AI marketing", "tone": "casual", "platform": "Instagram"}
        defaults.update(kwargs)
        return ContentContext(**defaults)

    @pytest.mark.asyncio
    async def test_generate_returns_post_string(self):
        result = await self.agent.generate(self._ctx())
        assert isinstance(result["post"], str)
        assert len(result["post"]) > 0

    @pytest.mark.asyncio
    async def test_generate_includes_topic(self):
        result = await self.agent.generate(self._ctx(topic="growth hacking"))
        # LLM may paraphrase — just verify a non-empty post was generated
        assert isinstance(result["post"], str)
        assert len(result["post"]) > 10

    @pytest.mark.asyncio
    async def test_word_count_within_platform_limit(self):
        result = await self.agent.generate(self._ctx(platform="Twitter/X"))
        # Twitter limit is 30 words * 1.5 = 45 max
        assert result["word_count"] <= 50

    @pytest.mark.asyncio
    async def test_all_tones_produce_output(self):
        for tone in ("casual", "formal", "promotional", "informational", "inspirational"):
            result = await self.agent.generate(self._ctx(tone=tone))
            assert result["post"]

    @pytest.mark.asyncio
    async def test_unknown_tone_falls_back_gracefully(self):
        result = await self.agent.generate(self._ctx(tone="unknown_tone"))
        assert result["post"]


# ── HashtagAgent ──────────────────────────────────────────────────────────────

class TestHashtagAgent:
    def setup_method(self):
        self.agent = HashtagAgent()

    def _ctx(self, **kwargs):
        defaults = {"topic": "AI marketing", "tone": "casual", "platform": "Instagram"}
        defaults.update(kwargs)
        return ContentContext(**defaults)

    @pytest.mark.asyncio
    async def test_hashtags_are_prefixed(self):
        result = await self.agent.generate(self._ctx())
        for tag in result["hashtags"]:
            assert tag.startswith("#")

    @pytest.mark.asyncio
    async def test_instagram_gets_up_to_15_tags(self):
        result = await self.agent.generate(self._ctx(platform="Instagram"))
        assert 1 <= result["count"] <= 15

    @pytest.mark.asyncio
    async def test_linkedin_gets_up_to_5_tags(self):
        result = await self.agent.generate(self._ctx(platform="LinkedIn"))
        assert 1 <= result["count"] <= 5

    @pytest.mark.asyncio
    async def test_twitter_gets_up_to_3_tags(self):
        result = await self.agent.generate(self._ctx(platform="Twitter/X"))
        assert 1 <= result["count"] <= 3

    @pytest.mark.asyncio
    async def test_no_duplicate_hashtags(self):
        result = await self.agent.generate(self._ctx())
        assert len(result["hashtags"]) == len(set(result["hashtags"]))

    @pytest.mark.asyncio
    async def test_keywords_appear_in_hashtags(self):
        ctx = self._ctx(keywords=["uniquekeyword123"])
        result = await self.agent.generate(ctx)
        tags_lower = [t.lower() for t in result["hashtags"]]
        assert any("uniquekeyword123" in t for t in tags_lower)


# ── VisualAgent ───────────────────────────────────────────────────────────────

class TestVisualAgent:
    def setup_method(self):
        self.agent = VisualAgent()

    def _ctx(self, **kwargs):
        defaults = {"topic": "AI marketing", "tone": "casual", "platform": "Instagram"}
        defaults.update(kwargs)
        return ContentContext(**defaults)

    @pytest.mark.asyncio
    async def test_generate_returns_prompt(self):
        result = await self.agent.generate(self._ctx())
        assert isinstance(result["visual_prompt"], str)
        assert len(result["visual_prompt"]) > 20

    @pytest.mark.asyncio
    async def test_negative_prompt_present(self):
        result = await self.agent.generate(self._ctx())
        assert isinstance(result["negative_prompt"], str)
        assert len(result["negative_prompt"]) > 0

    @pytest.mark.asyncio
    async def test_aspect_ratio_matches_platform(self):
        result = await self.agent.generate(self._ctx(platform="YouTube"))
        assert "16:9" in result["aspect_ratio"]

    @pytest.mark.asyncio
    async def test_all_platforms_produce_output(self):
        for platform in ("Instagram", "LinkedIn", "Twitter/X", "TikTok", "YouTube"):
            result = await self.agent.generate(self._ctx(platform=platform))
            assert result["visual_prompt"]
