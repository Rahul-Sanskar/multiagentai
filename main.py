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


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", env=settings.app_env, version=app.version)
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
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
