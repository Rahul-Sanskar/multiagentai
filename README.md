# Autonomous Social Media Growth Agent

A production-grade multi-agent AI system that turns raw social media data into a fully reviewed and published content calendar. Built with FastAPI, React, FAISS, and Groq (free LLM).

---

## What it does

1. Analyzes your posting history — tone, topics, engagement, content formats
2. Benchmarks against competitor content to find gaps and opportunities
3. Builds a RAG index from both reports for context-aware generation
4. Generates a multi-platform content calendar (up to 14 days)
5. Creates post copy, hashtags, and image prompts via LLM (Groq / Ollama)
6. Stores content for human review with targeted regeneration
7. Publishes approved posts to LinkedIn, X, and Instagram
8. Tracks post-publish engagement metrics and suggests calendar improvements

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    React Frontend (port 5173)                │
│  Pipeline · Calendar · Review · Publish                      │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP (proxied)
┌────────────────────────▼────────────────────────────────────┐
│                  FastAPI Backend (port 8000)                  │
│  /api/v1/pipeline/run  ·  /api/v1/reviews  ·  /api/v1/publish│
└────────────────────────┬────────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
┌───────▼──────┐ ┌───────▼──────┐ ┌──────▼──────────┐
│ Profile +    │ │  RAG Pipeline │ │  Calendar +     │
│ Competitor   │ │  FAISS index  │ │  HITL feedback  │
│ Agents       │ │  (persisted)  │ │  (persisted)    │
└──────────────┘ └───────────────┘ └─────────────────┘
        │
┌───────▼──────────────────────────────────────────────┐
│  Content Creation  (CopyAgent · HashtagAgent · Visual)│
│  LLM: Groq llama-3.3-70b-versatile → Ollama → template│
└───────────────────────────┬──────────────────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  Review → Approve → Publish │
              │  LinkedIn · X · Instagram   │
              └─────────────┬──────────────┘
                            │
              ┌─────────────▼──────────────┐
              │  Impact Tracker             │
              │  DB-backed scheduled fetch  │
              └────────────────────────────┘

Storage: SQLite (dev) · PostgreSQL (prod) · FAISS index on disk
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI, SQLAlchemy async, Pydantic v2 |
| LLM | Groq API (llama-3.3-70b-versatile) → Ollama fallback → templates |
| RAG | FAISS + sentence-transformers (all-MiniLM-L6-v2) |
| Frontend | React 18, TypeScript, Tailwind CSS, Vite |
| Database | SQLite (dev) / PostgreSQL (prod) via aiosqlite / asyncpg |
| Publishing | X API v2 (OAuth 1.0a), LinkedIn UGC API, Meta Graph API |
| Data ingestion | X API v2 Bearer Token (read-only) |

---

## Setup

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Clone and install backend

```bash
git clone https://github.com/Rahul-Sanskar/multiagentai.git
cd multiagentai

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in at minimum:

```env
DATABASE_URL=sqlite+aiosqlite:///./dev.db
SECRET_KEY=any-random-string

# LLM — get a free key at https://console.groq.com
GROQ_API_KEY=gsk_...

# X API (optional — for real data ingestion)
X_BEARER_TOKEN=...
X_API_KEY=...
X_API_SECRET=...
X_ACCESS_TOKEN=...
X_ACCESS_TOKEN_SECRET=...

# LinkedIn (optional — for real publishing)
LINKEDIN_ACCESS_TOKEN=...
LINKEDIN_PERSON_URN=urn:li:person:...
```

Without `GROQ_API_KEY` the system uses template fallbacks. Without X/LinkedIn credentials it uses mock data and simulation.

### 3. Install frontend

```bash
cd frontend
npm install
cd ..
```

---

## Running

### Backend (Terminal 1)

```bash
python -m uvicorn main:app --reload --port 8000
```

- API: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`

### Frontend (Terminal 2)

```bash
cd frontend
npm run dev
```

- UI: `http://localhost:5173`

### Docker (alternative — one command)

```bash
cp .env.example .env   # fill in GROQ_API_KEY at minimum
docker-compose up --build
```

API at `http://localhost:8000`, no frontend container (run separately).

---

## Using the UI

### Pipeline tab
1. Enter your posts (one per line) — or enter an X username to fetch real tweets
2. Enter competitor posts
3. Select platforms and number of days
4. Click **Run Pipeline**
5. All 8 stages run automatically — results appear below

### Calendar tab
Shows the generated 14-day content calendar after a pipeline run.

### Review tab
- Filter by status: pending / approved / revision
- Expand any card to see full copy, hashtags, and visual prompt
- Click **Approve**, **Rewrite copy**, **New hashtags**, or **New visual**

### Publish tab
- Lists all approved reviews
- Select target platforms per post
- Click **Publish** — real API if credentials are set, simulation otherwise
- Job status (posted / queued / failed) shown with URLs

---

## E2E Demo (no server needed)

```bash
python examples/e2e_test.py
```

Runs all 8 pipeline stages against a built-in AI engineer mock dataset. With `GROQ_API_KEY` set, content is real LLM output. Takes ~30–60 seconds.

Expected output:
```
All steps passed. Pipeline is healthy.
```

---

## API Usage

All endpoints are at `http://localhost:8000/api/v1`.

### Run full pipeline

```bash
curl -s -X POST http://localhost:8000/api/v1/pipeline/run \
  -H "Content-Type: application/json" \
  -d '{
    "my_posts": [
      {"text": "Just shipped a LangGraph pipeline.", "likes": 800, "timestamp": "2024-03-01T09:00:00Z"}
    ],
    "competitor_posts": [
      {"text": "LangGraph vs AutoGen: which wins?", "likes": 1800, "timestamp": "2024-03-02T09:00:00Z"}
    ],
    "x_username": "karpathy",
    "start_date": "2024-05-01",
    "days": 3,
    "platforms": ["LinkedIn"],
    "auto_approve": true
  }' | python -m json.tool
```

`x_username` is optional. If provided and `X_BEARER_TOKEN` is set, real tweets are fetched and used instead of `my_posts`. Falls back to `my_posts` on any API failure.

### Generate content

```bash
curl -s -X POST http://localhost:8000/api/v1/generate-content \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "building multi-agent systems with LangGraph",
    "platform": "LinkedIn",
    "tone": "informational",
    "keywords": ["LangGraph", "RAG", "multi-agent"]
  }' | python -m json.tool
```

### Review and publish

```bash
# List reviews
curl http://localhost:8000/api/v1/reviews

# Approve
curl -X PATCH http://localhost:8000/api/v1/reviews/1/status \
  -H "Content-Type: application/json" \
  -d '{"status": "approved"}'

# Publish
curl -X POST http://localhost:8000/api/v1/publish \
  -H "Content-Type: application/json" \
  -d '{"review_id": 1, "platforms": ["LinkedIn"]}'
```

---

## LLM Configuration

Priority chain — first available backend wins:

| Priority | Backend | Config |
|---|---|---|
| 1 | Groq | `GROQ_API_KEY=gsk_...` in `.env` — free at [console.groq.com](https://console.groq.com) |
| 2 | Ollama | Run `ollama serve` + `ollama pull llama3` locally — fully free |
| 3 | Templates | Always available — deterministic fallback, no AI |

Model used: `llama-3.3-70b-versatile` (Groq) / `llama3` (Ollama).

---

## X API Credentials

Get them at [developer.twitter.com](https://developer.twitter.com):

| Key | Where to find |
|---|---|
| `X_BEARER_TOKEN` | App → Keys and Tokens → Bearer Token |
| `X_API_KEY` | App → Keys and Tokens → API Key |
| `X_API_SECRET` | App → Keys and Tokens → API Key Secret |
| `X_ACCESS_TOKEN` | App → Keys and Tokens → Access Token (needs Read+Write) |
| `X_ACCESS_TOKEN_SECRET` | App → Keys and Tokens → Access Token Secret |

For publishing, set app permissions to **Read and Write** then regenerate the access tokens.

---

## Running Tests

```bash
# Fast unit tests (no coverage)
python -m pytest tests/ -q --no-cov

# With coverage report (enforced ≥ 70%)
python -m pytest tests/
```

---

## Project Structure

```
├── agents/          — AI agents (copy, hashtag, visual, profile, competitor)
├── api/             — FastAPI routers and schemas
├── db/              — SQLAlchemy models and repositories
├── orchestrator/    — Pipeline, calendar, content orchestrators
├── services/        — LLM, RAG, X API, publish, metrics, impact tracker
├── utils/           — NLP, logging, retry, validators
├── frontend/        — React + TypeScript + Tailwind UI
├── examples/        — E2E demo and run scripts
├── tests/           — 128 pytest tests
├── main.py          — FastAPI app entry point
├── config.py        — Pydantic settings
├── Dockerfile
└── docker-compose.yml
```

---

## Environment Variables Reference

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | Yes | `sqlite+aiosqlite:///./dev.db` for local |
| `SECRET_KEY` | Yes | Any random string |
| `GROQ_API_KEY` | Recommended | Free LLM — [console.groq.com](https://console.groq.com) |
| `X_BEARER_TOKEN` | Optional | Read tweets from X |
| `X_API_KEY` | Optional | Publish to X |
| `X_API_SECRET` | Optional | Publish to X |
| `X_ACCESS_TOKEN` | Optional | Publish to X |
| `X_ACCESS_TOKEN_SECRET` | Optional | Publish to X |
| `LINKEDIN_ACCESS_TOKEN` | Optional | Publish to LinkedIn |
| `LINKEDIN_PERSON_URN` | Optional | LinkedIn author URN |
| `INSTAGRAM_USER_ID` | Optional | Publish to Instagram |
| `INSTAGRAM_ACCESS_TOKEN` | Optional | Publish to Instagram |
| `IMPACT_FETCH_DELAY_SECONDS` | Optional | Default 3600 (1 hour) |

## 🎬 Demo Video

A full 10-minute walkthrough of the system is available here:

👉 https://drive.google.com/file/d/13_FWdskU3FcDY3zb2wl9CnSpmzyqQCG3/view?usp=drive_link

This demo covers:
- End-to-end pipeline execution
- Multi-agent architecture
- RAG pipeline
- Human-in-the-loop workflow
- Publishing system
- Real vs fallback API behavior
