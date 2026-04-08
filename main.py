from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from utils.logger import setup_logging, get_logger
from db.session import engine, Base

# ── Routers ───────────────────────────────────────────────────────────────────
from api.v1 import router as v1_router                          # pipeline endpoints
from api.routes import router as agent_router                   # generic agent runner
from api.intelligence_routes import router as intelligence_router
from api.rag_routes import router as rag_router
from api.calendar_routes import router as calendar_router
from api.content_creation_routes import router as content_router
from api.review_routes import router as review_router
from api.publish_routes import router as publish_router

# ── Middleware & error handlers ───────────────────────────────────────────────
from api.middleware import RequestIDMiddleware, AccessLogMiddleware
from api.errors import register_error_handlers

settings = get_settings()
setup_logging()
logger = get_logger("main")


def _ensure_nltk_data() -> None:
    """
    Download required NLTK packages at runtime if they are not already present.

    - Uses /app/nltk_data inside the container (writable, predictable path).
    - Falls back to ~/nltk_data if /app is not writable.
    - Adds the chosen directory to nltk.data.path so lookups work immediately.
    - Never raises — a download failure logs a warning but does not crash startup.
      The NLP utils degrade gracefully when data is missing.
    """
    import nltk
    import os

    # Prefer /app/nltk_data (always writable in Railway/Docker containers).
    # Fall back to the home directory for local dev.
    candidates = ["/app/nltk_data", os.path.join(os.path.expanduser("~"), "nltk_data")]
    nltk_dir = next((d for d in candidates if os.access(os.path.dirname(d) or "/", os.W_OK)), candidates[-1])

    os.makedirs(nltk_dir, exist_ok=True)

    # Prepend so this directory is checked first on every nltk.data.find() call.
    if nltk_dir not in nltk.data.path:
        nltk.data.path.insert(0, nltk_dir)

    packages = [
        ("punkt",     "tokenizers/punkt"),
        ("punkt_tab", "tokenizers/punkt_tab"),
        ("stopwords", "corpora/stopwords"),
    ]

    for pkg, resource_path in packages:
        try:
            nltk.data.find(resource_path)
            logger.info("nltk_data_ok", package=pkg)
        except LookupError:
            try:
                nltk.download(pkg, download_dir=nltk_dir, quiet=True, raise_on_error=True)
                logger.info("nltk_data_downloaded", package=pkg, dir=nltk_dir)
            except Exception as exc:
                # Network unavailable or quota exceeded — log and continue.
                # NLP features will fall back to basic tokenisation.
                logger.warning("nltk_data_download_failed", package=pkg, error=str(exc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", env=settings.app_env, version=app.version)

    _ensure_nltk_data()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Re-queue any impact fetches that were pending when the server last stopped
    from services.impact_tracker import recover_pending_fetches
    from db.session import AsyncSessionLocal
    recovered = await recover_pending_fetches(AsyncSessionLocal)
    if recovered:
        logger.info("startup_impact_recovery", recovered=recovered)

    yield
    logger.info("shutdown")
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Multi-agent AI content pipeline",
    debug=settings.debug,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── Middleware (order matters — first added = outermost) ──────────────────────
app.add_middleware(AccessLogMiddleware)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# ── Error handlers ────────────────────────────────────────────────────────────
register_error_handlers(app)

# ── Routes ────────────────────────────────────────────────────────────────────
app.include_router(v1_router)           # /api/v1/analyze-profile, etc.
app.include_router(agent_router)        # /api/v1/run, /api/v1/runs
app.include_router(intelligence_router) # /api/v1/intelligence/*
app.include_router(rag_router)          # /api/v1/rag/*
app.include_router(calendar_router)     # /api/v1/calendar/*
app.include_router(content_router)      # /api/v1/content/*
app.include_router(review_router)       # /api/v1/reviews/*
app.include_router(publish_router)      # /api/v1/publish/jobs, /metrics


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "env": settings.app_env, "version": app.version}
