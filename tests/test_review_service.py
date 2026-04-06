"""Tests for services/review_service.py"""
import pytest
import pytest_asyncio
from agents.content_context import ContentContext
from services import review_service


def _ctx(**kwargs):
    defaults = {
        "topic": "AI marketing",
        "tone": "casual",
        "platform": "Instagram",
        "keywords": ["ai", "marketing"],
    }
    defaults.update(kwargs)
    return ContentContext(**defaults)


class TestCreateReview:
    @pytest.mark.asyncio
    async def test_creates_pending_review(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        assert review["status"] == "pending"
        assert review["id"] > 0
        assert review["post"]
        assert isinstance(review["hashtags"], list)
        assert review["visual_prompt"]

    @pytest.mark.asyncio
    async def test_review_stores_topic(self, db_session):
        review = await review_service.create_review(db_session, _ctx(topic="growth hacking"))
        await db_session.flush()
        assert review["topic"] == "growth hacking"

    @pytest.mark.asyncio
    async def test_review_stores_platform(self, db_session):
        review = await review_service.create_review(db_session, _ctx(platform="LinkedIn"))
        await db_session.flush()
        assert review["platform"] == "LinkedIn"


class TestSetStatus:
    @pytest.mark.asyncio
    async def test_approve_review(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        updated = await review_service.set_status(db_session, review["id"], "approved", note="LGTM")
        assert updated["status"] == "approved"
        assert updated["reviewer_note"] == "LGTM"

    @pytest.mark.asyncio
    async def test_request_revision(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        updated = await review_service.set_status(db_session, review["id"], "revision")
        assert updated["status"] == "revision"

    @pytest.mark.asyncio
    async def test_invalid_status_raises(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        with pytest.raises(ValueError):
            await review_service.set_status(db_session, review["id"], "rejected")

    @pytest.mark.asyncio
    async def test_not_found_raises(self, db_session):
        with pytest.raises(KeyError):
            await review_service.set_status(db_session, 99999, "approved")


class TestRegenerate:
    @pytest.mark.asyncio
    async def test_regenerate_hashtags_only_changes_hashtags(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        original_post = review["post"]

        updated = await review_service.regenerate(
            db_session, review["id"], action="regenerate_hashtags", note="test"
        )
        # Post should be unchanged
        assert updated["post"] == original_post
        # Status should be revision
        assert updated["status"] == "revision"

    @pytest.mark.asyncio
    async def test_rewrite_post_only_changes_post(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        original_hashtags = review["hashtags"]

        updated = await review_service.regenerate(
            db_session, review["id"], action="rewrite_post"
        )
        assert updated["hashtags"] == original_hashtags

    @pytest.mark.asyncio
    async def test_invalid_action_raises(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        with pytest.raises(ValueError, match="Unknown action"):
            await review_service.regenerate(db_session, review["id"], action="invalid_action")

    @pytest.mark.asyncio
    async def test_revision_history_recorded(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        updated = await review_service.regenerate(
            db_session, review["id"], action="regenerate_hashtags", note="needs niche tags"
        )
        assert len(updated["revision_history"]) >= 1
        assert updated["revision_history"][-1]["note"] == "needs niche tags"


class TestManualEdit:
    @pytest.mark.asyncio
    async def test_manual_edit_post(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        updated = await review_service.manual_edit(
            db_session, review["id"], field="post", value="My custom post text", note="manual"
        )
        assert updated["post"] == "My custom post text"

    @pytest.mark.asyncio
    async def test_invalid_field_raises(self, db_session):
        review = await review_service.create_review(db_session, _ctx())
        await db_session.flush()
        with pytest.raises(ValueError, match="not editable"):
            await review_service.manual_edit(
                db_session, review["id"], field="status", value="approved"
            )
