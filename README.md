# MultiAgentAI — Social Media Content Pipeline

An async, multi-agent AI system that turns raw social media data into a fully reviewed and published content calendar. Built with FastAPI, LangChain, and OpenAI GPT-4o.

---

## Overview

MultiAgentAI orchestrates a chain of specialized AI agents to automate the entire content creation workflow:

- Analyze your posting history and extract writing style, topics, and engagement patterns
- Benchmark against competitor content to surface gaps and opportunities
- Build a RAG index from both reports for context-aware content generation
- Generate a multi-platform content calendar
- Create post copy, hashtags, and image prompts in parallel
- Store content for human review, then publish on approval

The pipeline can run fully automated (`auto_approve=True`) or with a human-in-the-loop review step between generation and publishing.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                       │
│  /api/v1/*  ·  /docs  ·  /health                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                ┌────────────▼────────────┐
                │   PipelineOrchestrator  │
                │  (chains all 8 stages)  │
                └────────────┬────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼───────┐   ┌────────▼────────┐   ┌──────▼──────────┐
│ ProfileIntel  │   │  Competitor     │   │  RAG Pipeline   │
│ ligenceAgent  │   │  AnalysisAgent  │   │  (FAISS index)  │
│               │   │                 │   │                 │
│ · writing     │   │ · content gaps  │   │ · ingest        │
│   style       │   │ · trending      │   │ · retrieve      │
│ · topics      │   │   topics        │   │ · enrich ctx    │
│ · engagement  │   │ · top formats   │   │                 │
└───────────────┘   └─────────────────┘   └─────────────────┘
                             │
                ┌────────────▼────────────┐
                │  CalendarOrchestrator   │
                │  · 14-day schedule      │
                │  · HITL feedback loop   │
                └────────────┬────────────┘
                             │
                ┌────────────▼────────────┐
                │ ContentCreationOrch.    │  ← runs in parallel
                │  ┌──────────────────┐   │
                │  │   CopyAgent      │   │  GPT-4o + template fallback
                │  │   HashtagAgent   │   │  GPT-4o + keyword bank fallback
                │  │   VisualAgent    │   │  GPT-4o + rule-based fallback
                │  └──────────────────┘   │
                └────────────┬────────────┘
                             │
                ┌────────────▼────────────┐
                │     ReviewService       │
                │  · persist as pending   │
                │  · approve / revise     │
                └────────────┬────────────┘
                             │
                ┌────────────▼────────────┐
                │     PublishService      │
                │  · per-platform jobs    │
                │  · latency metrics      │
                │  · schedule support     │
                └─────────────────────────┘

External integrations
  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
  │  OpenAI API  │   │  X (Twitter) │   │  SQLite /    │
  │  GPT-4o      │   │  API v2      │   │  PostgreSQL  │
  └──────────────┘   └──────────────┘   └──────────────┘
```

---

## Features

**Agents**
- `ProfileIntelligenceAgent` — writing style detection, topic extraction (bigrams/trigrams), engagement analytics, posting frequency
- `CompetitorAnalysisAgent` — content gap analysis, trending topic detection, format benchmarking
- `CopyAgent` — LLM-generated post copy per platform and tone, template fallback
- `HashtagAgent` — 8–12 niche hashtags via LLM, keyword-bank fallback
- `VisualAgent` — detailed Midjourney/DALL-E image prompts, rule-based fallback

**Pipeline**
- 8-stage orchestrated pipeline with per-stage error isolation
- RAG-enriched content context using FAISS vector search
- Human-in-the-loop calendar feedback with audit trail
- Auto-approve mode for fully automated runs
- Structured publish jobs with latency tracking and per-platform metrics

**API**
- RESTful FastAPI with OpenAPI docs at `/docs`
- Request ID middleware and structured JSON logging
- Consistent `ApiResponse[T]` envelope on all endpoints
- Health check at `/health`

**Data**
- X (Twitter) API v2 integration with `USE_REAL_API` toggle and mock fallback
- Async SQLAlchemy with SQLite (dev) or PostgreSQL (prod)

---

## Setup

**Requirements:** Python 3.10+

### 1. Clone and install dependencies

```bash
git clone https://github.com/your-org/multiagentai.git
cd multiagentai
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
OPENAI_API_KEY=sk-...            # required for LLM generation
DEFAULT_MODEL=gpt-4o

DATABASE_URL=sqlite+aiosqlite:///./dev.db   # or PostgreSQL URL

X_BEARER_TOKEN=                  # optional — leave blank to use mock data
SECRET_KEY=change-me-in-production
```

### 3. Start the server

```bash
uvicorn main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`

---

## API Usage

All endpoints are prefixed with `/api/v1`. Responses use the envelope:

```json
{ "success": true, "data": { ... }, "request_id": "...", "timestamp": "..." }
```

### Analyze a profile

```bash
curl -X POST http://localhost:8000/api/v1/analyze-profile \
  -H "Content-Type: application/json" \
  -d '{
    "posts": [
      {
        "text": "5 tips to grow your business on social media. Thread below",
        "timestamp": "2024-01-03T11:00:00",
        "likes": 340, "comments": 42, "shares": 88, "views": 5000
      }
    ]
  }'
```

### Generate a content calendar

```bash
curl -X POST http://localhost:8000/api/v1/generate-calendar \
  -H "Content-Type: application/json" \
  -d '{
    "profile_report": { ... },
    "competitor_report": { ... },
    "start_date": "2024-02-01",
    "days": 7
  }'
```

### Generate post content

```bash
curl -X POST http://localhost:8000/api/v1/generate-content \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "AI productivity tools",
    "platform": "LinkedIn",
    "tone": "informational",
    "keywords": ["automation", "LLM", "workflow"]
  }'
```

### Run the full pipeline

```bash
curl -X POST http://localhost:8000/api/v1/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{
    "my_posts": [ { "text": "...", "likes": 120, "timestamp": "2024-01-01T09:00:00" } ],
    "competitor_posts": [ { "text": "...", "likes": 500, "timestamp": "2024-01-02T10:00:00" } ],
    "start_date": "2024-02-01",
    "days": 5,
    "platforms": ["Instagram", "LinkedIn"],
    "auto_approve": true
  }'
```

### Review and publish

```bash
# List pending reviews
curl http://localhost:8000/api/v1/reviews

# Approve a review
curl -X POST http://localhost:8000/api/v1/reviews/1/approve

# Publish an approved review
curl -X POST http://localhost:8000/api/v1/publish \
  -H "Content-Type: application/json" \
  -d '{ "review_id": 1, "platforms": ["Instagram", "LinkedIn"] }'
```

### RAG index

```bash
# Ingest a report
curl -X POST http://localhost:8000/api/v1/rag/ingest \
  -H "Content-Type: application/json" \
  -d '{ "report": { ... }, "source": "profile_report" }'

# Query for context
curl -X POST http://localhost:8000/api/v1/rag/query \
  -H "Content-Type: application/json" \
  -d '{ "query": "high engagement content formats", "top_k": 5 }'
```

---

## Demo

Run the full pipeline locally without starting the server:

```bash
python examples/run_agents.py
```

This executes all 8 stages against sample data and prints a structured summary:

```
== STAGE RESULTS ==
  ✓ profile_analysis
  ✓ competitor_analysis
  ✓ rag_ingestion
  ✓ calendar_generation
  ✓ content_and_review
  ✓ auto_approve
  ✓ publish
  calendar entries : 10
  reviews created  : 10
  publish jobs     : 10 posted / 0 failed

== CALENDAR ==
  Day  1 | 2024-02-01 | Instagram    | short-form video  | 09:00 | AI productivity tools
  Day  2 | 2024-02-02 | LinkedIn     | thought leadership| 11:00 | multi-agent systems
  ...

== PUBLISH METRICS ==
  Global  attempts=20  success=20  failed=0  success_rate=100%  avg_latency=12ms
```

To test with real X (Twitter) data, set your bearer token in `.env` and update `USE_REAL_API` in `services/x_api_client.py`:

```python
USE_REAL_API = True
```

Then fetch posts directly:

```python
from services.x_api_client import fetch_user_posts
posts = await fetch_user_posts("username", max_results=15)
```

---

## Project Structure

```
├── agents/          # Individual AI agents (copy, hashtag, visual, profile, etc.)
├── api/             # FastAPI routers and request/response schemas
├── db/              # SQLAlchemy models, session, and repositories
├── orchestrator/    # Pipeline, calendar, and content creation orchestrators
├── services/        # LLM service, RAG pipeline, X API client, publish service
├── utils/           # NLP utilities, logging, retry, validators
├── examples/        # End-to-end demo script
├── tests/           # Pytest test suite
├── main.py          # FastAPI application entry point
└── config.py        # Pydantic settings (loaded from .env)
```

---

## Running Tests

```bash
pytest tests/ -v
```

With coverage:

```bash
pytest tests/ --cov=. --cov-report=term-missing
```
