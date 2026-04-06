"""
Shared pytest fixtures.
Uses an in-memory SQLite database so tests are fully isolated.
"""
from __future__ import annotations

import asyncio
import logging

import pytest
import pytest_asyncio
import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from db.session import Base

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


def _configure_test_logging() -> None:
    """
    Configure structlog for the test environment.

    The default PrintLoggerFactory produces PrintLogger objects which have no
    .name attribute — this breaks structlog.stdlib.add_logger_name and causes
    AttributeError across every test that touches any logger.

    Fix: use stdlib.LoggerFactory() so loggers are real logging.Logger instances.
    Suppress output below WARNING to keep test output clean.
    """
    logging.basicConfig(level=logging.WARNING)
    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(colors=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )


# Apply before any module-level get_logger() calls fire
_configure_test_logging()


@pytest.fixture(scope="session")
def event_loop():
    """Single event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def db_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    """Fresh session per test, rolled back after each test."""
    session_factory = async_sessionmaker(
        bind=db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture(scope="session", autouse=True)
def _disable_metrics_persistence():
    """Prevent tests from writing metrics to disk."""
    import services.metrics as _m
    original = _m.METRICS_PATH
    _m.METRICS_PATH = None
    _m.metrics._path = None
    yield
    _m.METRICS_PATH = original


@pytest.fixture(scope="session", autouse=True)
def _disable_calendar_persistence(tmp_path_factory):
    """Redirect calendar session persistence to a temp dir during tests."""
    from orchestrator import calendar_state as _cs
    tmp = tmp_path_factory.mktemp("calendar")
    _cs.calendar_store._path = tmp / "sessions.json"
    yield


# ── Sample data fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def sample_posts():
    return [
        {"text": "AI is transforming marketing in 2024.", "timestamp": "2024-01-01T09:00:00",
         "likes": 120, "comments": 15, "shares": 30, "views": 2000},
        {"text": "5 tips to grow your business on social media.",
         "timestamp": "2024-01-03T11:00:00", "likes": 340, "comments": 42, "shares": 88, "views": 5000},
        {"text": "New blog post: content marketing strategies.",
         "timestamp": "2024-01-05T14:00:00", "likes": 210, "comments": 28, "shares": 12, "views": 3100},
    ]


@pytest.fixture
def sample_competitor_posts():
    return [
        {"text": "Watch our video on AI tools for marketers.",
         "timestamp": "2024-01-02T10:00:00", "likes": 500, "comments": 80, "shares": 150,
         "views": 9000, "format": "video"},
        {"text": "Top 10 automation tools every startup needs.",
         "timestamp": "2024-01-04T09:00:00", "likes": 620, "comments": 95, "shares": 200, "views": 11000},
        {"text": "Growth hacking with short-form video case study.",
         "timestamp": "2024-01-06T11:00:00", "likes": 430, "comments": 60, "shares": 110,
         "views": 7500, "format": "video"},
    ]


@pytest.fixture
def sample_profile_report(sample_posts):
    from agents.profile_intelligence_agent import ProfileIntelligenceAgent
    return ProfileIntelligenceAgent().analyze(sample_posts)


@pytest.fixture
def sample_competitor_report(sample_profile_report, sample_competitor_posts):
    from agents.competitor_analysis_agent import CompetitorAnalysisAgent
    return CompetitorAnalysisAgent().analyze(sample_profile_report, sample_competitor_posts)
