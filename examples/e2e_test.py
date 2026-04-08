"""
MultiAgentAI — End-to-End System Demo
======================================
Persona  : Alex Chen — Senior AI Engineer & Developer Advocate
           Writes about LLMs, multi-agent systems, RAG, MLOps, and
           open-source tooling. Audience: ML engineers and AI builders.

Pipeline : Profile → Competitor → RAG → Calendar → HITL → Content → Review → Publish

Toggle
------
    USE_REAL_API = True   → fetch posts from X API (free tier), fallback to mock on error
    USE_REAL_API = False  → use built-in mock dataset (default, no credentials needed)

Run:
    python examples/e2e_test.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
import time
import traceback
from datetime import datetime
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Toggle ────────────────────────────────────────────────────────────────────
USE_REAL_API: bool = False
MY_X_USERNAME: str = ""   # e.g. "karpathy"
COMPETITOR_QUERIES: list[str] = [
    "LangGraph multi-agent -is:retweet",
    "RAG pipeline production LLM -is:retweet",
    "MLOps LLM deployment -is:retweet",
]

# ── ANSI colours ──────────────────────────────────────────────────────────────
RESET  = "\033[0m"
BOLD   = "\033[1m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
DIM    = "\033[2m"
WHITE  = "\033[97m"


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


# ── Print helpers ─────────────────────────────────────────────────────────────

def banner() -> None:
    print(f"\n{BOLD}{CYAN}{'━' * 64}{RESET}")
    print(f"{BOLD}{CYAN}  MultiAgentAI  ·  End-to-End System Demo{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 64}{RESET}")
    print(f"  Persona  : {WHITE}Alex Chen — Senior AI Engineer & Developer Advocate{RESET}")
    print(f"  Topics   : {DIM}LLMs · multi-agent systems · RAG · MLOps · open-source{RESET}")
    print(f"  Mode     : {BOLD}{'REAL X API' if USE_REAL_API else 'MOCK DATASET'}{RESET}")
    print(f"  Started  : {DIM}{datetime.now().strftime('%Y-%m-%d  %H:%M:%S')}{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 64}{RESET}\n")


def section(title: str, step: str = "") -> None:
    tag = f"  {CYAN}{step}{RESET}  " if step else "  "
    print(f"\n{BOLD}{'─' * 64}{RESET}")
    print(f"{BOLD}{tag}{WHITE}{title}{RESET}")
    print(f"{BOLD}{'─' * 64}{RESET}")


def log_step(label: str) -> None:
    print(f"\n{CYAN}{BOLD}  ▶  {label}{RESET}  {DIM}[{_ts()}]{RESET}")


def log_ok(label: str, detail: str = "") -> None:
    suffix = f"  {DIM}{detail}{RESET}" if detail else ""
    print(f"  {GREEN}✓  {label}{RESET}{suffix}")


def log_warn(msg: str) -> None:
    print(f"  {YELLOW}⚠  {msg}{RESET}")


def log_error(label: str, err: str) -> None:
    print(f"  {RED}✗  {label}  →  {err}{RESET}")


def kv(key: str, value: Any, indent: int = 4) -> None:
    pad = " " * indent
    print(f"{pad}{DIM}{key:<22}{RESET}{WHITE}{value}{RESET}")


def bullet(text: str, colour: str = DIM, indent: int = 6) -> None:
    pad = " " * indent
    print(f"{pad}{colour}•  {text}{RESET}")


# ── Validation helpers ────────────────────────────────────────────────────────

def assert_non_empty(value: Any, label: str) -> None:
    if value is None or value == "" or value == [] or value == {}:
        raise AssertionError(f"EMPTY OUTPUT: {label}")


def assert_keys(d: dict, keys: list[str], label: str) -> None:
    missing = [k for k in keys if k not in d]
    if missing:
        raise AssertionError(f"MISSING KEYS {missing} in {label}")


def assert_json_serialisable(obj: Any, label: str) -> None:
    try:
        json.dumps(obj, default=str)
    except Exception as exc:
        raise AssertionError(f"NOT JSON-SERIALISABLE {label}: {exc}")


# ── Realistic AI engineer profile data ───────────────────────────────────────

# Alex Chen's own posts — AI engineer writing about LLMs, agents, RAG, MLOps
_MY_POSTS: list[dict] = [
    {
        "text": (
            "Just shipped v2 of our multi-agent orchestration layer using LangGraph. "
            "The state machine approach makes complex agent handoffs surprisingly clean. "
            "Thread on what we learned building production agentic systems 🧵"
        ),
        "timestamp": "2024-03-01T09:15:00Z",
        "likes": 847, "comments": 134, "shares": 312, "views": 38400,
        "format": "thread",
    },
    {
        "text": (
            "RAG is not just 'embed + retrieve'. The real work is in chunking strategy, "
            "metadata filtering, and re-ranking. Here's the architecture we use in prod "
            "that cut hallucinations by 60%:"
        ),
        "timestamp": "2024-03-03T11:00:00Z",
        "likes": 1203, "comments": 198, "shares": 445, "views": 54200,
        "format": "thread",
    },
    {
        "text": (
            "Hot take: most teams fine-tune too early. "
            "A well-engineered RAG pipeline with GPT-4o will outperform a fine-tuned "
            "smaller model on domain tasks — and costs less to maintain. "
            "Fight me in the replies."
        ),
        "timestamp": "2024-03-05T14:30:00Z",
        "likes": 2341, "comments": 387, "shares": 621, "views": 91000,
        "format": "short-text",
    },
    {
        "text": (
            "New blog post: 'Evaluating LLM outputs at scale without losing your mind.' "
            "Covers LLM-as-judge, reference-free evals, and the traps we fell into. "
            "Link in bio 👇"
        ),
        "timestamp": "2024-03-07T10:00:00Z",
        "likes": 534, "comments": 67, "shares": 189, "views": 22100,
        "format": "link",
    },
    {
        "text": (
            "Spent the weekend benchmarking embedding models for a semantic search use case. "
            "Results were surprising — text-embedding-3-large didn't always win. "
            "Sharing the full comparison table:"
        ),
        "timestamp": "2024-03-09T08:00:00Z",
        "likes": 978, "comments": 143, "shares": 267, "views": 41300,
        "format": "image",
    },
    {
        "text": (
            "The hardest part of building AI products isn't the model — it's the eval loop. "
            "You need to know when your system regresses before your users do. "
            "Here's the lightweight eval framework we open-sourced:"
        ),
        "timestamp": "2024-03-11T09:30:00Z",
        "likes": 1567, "comments": 212, "shares": 498, "views": 67800,
        "format": "link",
    },
    {
        "text": (
            "Prompt caching with Claude and GPT-4o is genuinely underrated. "
            "We cut our inference costs by 40% on long-context tasks just by "
            "restructuring prompts to maximise cache hits. Quick breakdown:"
        ),
        "timestamp": "2024-03-13T11:00:00Z",
        "likes": 1089, "comments": 156, "shares": 334, "views": 48900,
        "format": "thread",
    },
    {
        "text": (
            "Unpopular opinion: structured outputs (JSON mode, function calling) "
            "are more important than model size for production reliability. "
            "A GPT-4o-mini with strict output schemas beats GPT-4 with free-form prompts "
            "every time in a pipeline."
        ),
        "timestamp": "2024-03-15T13:00:00Z",
        "likes": 1834, "comments": 276, "shares": 512, "views": 78200,
        "format": "short-text",
    },
    {
        "text": (
            "We just crossed 500 GitHub stars on our LangGraph agent template repo. "
            "Thank you to everyone who contributed issues, PRs, and feedback. "
            "More patterns coming this month 🙏"
        ),
        "timestamp": "2024-03-17T16:00:00Z",
        "likes": 723, "comments": 98, "shares": 87, "views": 31200,
        "format": "short-text",
    },
    {
        "text": (
            "MLOps for LLM apps is a different beast than classical ML. "
            "No training pipelines, but you need: prompt versioning, output logging, "
            "latency budgets, cost tracking, and drift detection. "
            "Here's the stack we landed on:"
        ),
        "timestamp": "2024-03-19T10:00:00Z",
        "likes": 1456, "comments": 189, "shares": 423, "views": 62400,
        "format": "thread",
    },
]

# Competitor posts — other AI engineers and developer advocates
_COMPETITOR_POSTS: list[dict] = [
    {
        "text": (
            "We rebuilt our entire data pipeline using LangGraph and the difference is night "
            "and day. Conditional edges + persistent state = no more spaghetti agent code. "
            "Full walkthrough:"
        ),
        "timestamp": "2024-03-02T09:00:00Z",
        "likes": 1923, "comments": 287, "shares": 634, "views": 82000,
        "format": "thread",
    },
    {
        "text": (
            "Agentic AI in 2024: the gap between demos and production is still massive. "
            "The teams shipping real value are the ones who treat agents as unreliable "
            "components and build accordingly — retries, fallbacks, human escalation."
        ),
        "timestamp": "2024-03-04T11:30:00Z",
        "likes": 3102, "comments": 445, "shares": 891, "views": 124000,
        "format": "short-text",
    },
    {
        "text": (
            "Vector databases compared: Pinecone vs Weaviate vs pgvector for production RAG. "
            "We ran 6 months of load tests. Here's what actually matters at scale:"
        ),
        "timestamp": "2024-03-06T10:00:00Z",
        "likes": 2456, "comments": 312, "shares": 712, "views": 98000,
        "format": "image",
    },
    {
        "text": (
            "The LLM observability space is finally maturing. "
            "LangSmith, Langfuse, and Helicone each have a different sweet spot. "
            "Here's how to choose based on your team size and stack:"
        ),
        "timestamp": "2024-03-08T09:00:00Z",
        "likes": 1678, "comments": 234, "shares": 489, "views": 71000,
        "format": "thread",
    },
    {
        "text": (
            "Open-sourcing our internal prompt testing harness. "
            "1000 stars in 48 hours — clearly this was a gap. "
            "It handles regression testing, A/B prompt comparison, and LLM-as-judge scoring."
        ),
        "timestamp": "2024-03-10T08:00:00Z",
        "likes": 4231, "comments": 567, "shares": 1203, "views": 167000,
        "format": "link",
    },
    {
        "text": (
            "Multimodal RAG is the next frontier. "
            "We're indexing PDFs, diagrams, and code snippets together and the retrieval "
            "quality on mixed-format enterprise docs is dramatically better. Demo thread:"
        ),
        "timestamp": "2024-03-12T11:00:00Z",
        "likes": 1345, "comments": 178, "shares": 398, "views": 57000,
        "format": "thread",
    },
    {
        "text": (
            "Cost optimisation for LLM apps: the low-hanging fruit most teams miss. "
            "1. Route simple queries to smaller models. "
            "2. Cache aggressively. "
            "3. Batch where latency allows. "
            "We cut costs 55% without touching model quality."
        ),
        "timestamp": "2024-03-14T10:00:00Z",
        "likes": 2789, "comments": 356, "shares": 823, "views": 109000,
        "format": "thread",
    },
    {
        "text": (
            "AI safety for production apps isn't just about alignment — it's about "
            "guardrails, output validation, and graceful degradation. "
            "Here's the practical checklist we use before every LLM feature ships:"
        ),
        "timestamp": "2024-03-16T09:30:00Z",
        "likes": 1987, "comments": 267, "shares": 612, "views": 84000,
        "format": "link",
    },
    {
        "text": (
            "Just published: 'The State of LLM Tooling in 2024.' "
            "Surveyed 200 AI engineers on what they're actually using in production. "
            "The results might surprise you."
        ),
        "timestamp": "2024-03-18T10:00:00Z",
        "likes": 3456, "comments": 489, "shares": 978, "views": 138000,
        "format": "link",
    },
    {
        "text": (
            "Streaming LLM responses in production: it's not just a UX nicety. "
            "Streaming lets you implement early stopping, token budget enforcement, "
            "and real-time output validation. Here's how we do it:"
        ),
        "timestamp": "2024-03-20T11:00:00Z",
        "likes": 1234, "comments": 167, "shares": 345, "views": 52000,
        "format": "thread",
    },
]


# ── Data loading ──────────────────────────────────────────────────────────────

async def load_data() -> tuple[list[dict], list[dict], str, str]:
    import services.data_loader as _dl
    from services.data_loader import load_my_posts, load_competitor_posts

    log_step("Loading profile and competitor data")

    # Inject the realistic AI engineer dataset into the data loader's mock pool
    _dl.MOCK_MY_POSTS         = _MY_POSTS          # type: ignore[attr-defined]
    _dl.MOCK_COMPETITOR_POSTS = _COMPETITOR_POSTS   # type: ignore[attr-defined]

    my_posts, my_src = await load_my_posts(
        use_real_api=USE_REAL_API,
        username=MY_X_USERNAME,
        max_results=10,
    )
    comp_posts, comp_src = await load_competitor_posts(
        use_real_api=USE_REAL_API,
        queries=COMPETITOR_QUERIES,
        max_per_query=5,
    )

    kv("Mode",             "REAL X API" if USE_REAL_API else "MOCK DATASET")
    kv("Own posts",        f"{len(my_posts)}  ({my_src})")
    kv("Competitor posts", f"{len(comp_posts)}  ({comp_src})")

    if USE_REAL_API and my_src == "mock":
        log_warn("X API unavailable for own posts — using mock data")
    if USE_REAL_API and comp_src == "mock":
        log_warn("X API unavailable for competitor posts — using mock data")

    assert_non_empty(my_posts, "my_posts")
    assert_non_empty(comp_posts, "competitor_posts")

    log_ok("Data loaded", f"own={len(my_posts)}  competitor={len(comp_posts)}")
    return my_posts, comp_posts, my_src, comp_src


# ── Step 1: Profile Intelligence ─────────────────────────────────────────────

async def step1_profile(posts: list[dict]) -> dict:
    from agents.profile_intelligence_agent import ProfileIntelligenceAgent

    log_step("Step 1 of 8  —  Profile Intelligence")
    agent = ProfileIntelligenceAgent()
    report = agent.analyze(posts)

    assert_non_empty(report, "profile_report")
    assert_keys(report, ["post_count", "writing_style", "topics", "posting_frequency", "engagement"], "profile_report")
    assert_json_serialisable(report, "profile_report")

    section("PROFILE INTELLIGENCE REPORT", "01")
    ws  = report["writing_style"]
    eng = report["engagement"]
    frq = report["posting_frequency"]
    kws = report["topics"]["top_keywords"]

    kv("Posts analysed",   report["post_count"])
    kv("Detected tone",    ws["tone"])
    kv("Avg sentence len", f"{ws['avg_sentence_length']} words")
    kv("Avg post length",  f"{ws['avg_post_length_words']} words")
    kv("Avg likes",        eng["avg_likes"])
    kv("Avg engagement",   f"{eng['avg_engagement_rate']}%")
    kv("Peak hour (UTC)",  frq.get("peak_hour_utc", "N/A"))
    kv("Peak weekday",     frq.get("peak_weekday", "N/A"))
    print(f"\n    {DIM}Top topics extracted:{RESET}")
    for kw in kws[:10]:
        bullet(kw, WHITE)

    log_ok("Profile Intelligence", f"tone={ws['tone']}  topics={len(kws)}")
    return report


# ── Step 2: Competitor Analysis ───────────────────────────────────────────────

async def step2_competitor(profile_report: dict, competitor_posts: list[dict]) -> dict:
    from agents.competitor_analysis_agent import CompetitorAnalysisAgent

    log_step("Step 2 of 8  —  Competitor Analysis")
    agent = CompetitorAnalysisAgent()
    report = agent.analyze(profile_report, competitor_posts)

    assert_non_empty(report, "competitor_report")
    assert_keys(report, ["content_gaps", "trending_topics", "high_performing_formats"], "competitor_report")
    assert_json_serialisable(report, "competitor_report")

    section("COMPETITOR ANALYSIS", "02")
    gaps = report["content_gaps"]

    print(f"    {DIM}Content gaps  —  topics competitors cover that you don't:{RESET}")
    for g in gaps["gaps"][:6]:
        bullet(g, YELLOW)

    print(f"\n    {DIM}Trending topics  (ranked by avg engagement):{RESET}")
    for t in report["trending_topics"][:5]:
        bullet(f"{t['keyword']:<30}  avg engagement: {t['avg_engagement_per_mention']:.0f}", WHITE)

    print(f"\n    {DIM}High-performing formats:{RESET}")
    for f in report["high_performing_formats"][:4]:
        bullet(f"{f['format']:<20}  avg eng: {f['avg_engagement']:.0f}   posts: {f['post_count']}", WHITE)

    kv("\n    Keyword overlap",  len(gaps["overlap"]))
    kv("    Unique to you",     len(gaps["unique_to_profile"]))
    kv("    Gaps to address",   len(gaps["gaps"]))

    log_ok("Competitor Analysis", f"gaps={len(gaps['gaps'])}  trending={len(report['trending_topics'])}")
    return report


# ── Step 3: RAG Pipeline ──────────────────────────────────────────────────────

async def step3_rag(profile_report: dict, competitor_report: dict) -> Any:
    from services.rag_pipeline import RAGPipeline, _HASHES_PATH
    from pathlib import Path

    log_step("Step 3 of 8  —  RAG Pipeline  (ingest + semantic retrieval)")

    # Clear stale hashes so the e2e test always re-indexes fresh data
    Path(_HASHES_PATH).unlink(missing_ok=True)

    rag = RAGPipeline()
    n1 = rag.ingest(profile_report, source="profile_report")
    n2 = rag.ingest(competitor_report, source="competitor_report")

    assert rag.chunk_count > 0, "RAG index is empty after ingestion"
    assert_json_serialisable(rag.stats(), "rag_stats")

    section("RAG PIPELINE  —  INDEX & RETRIEVAL", "03")
    stats = rag.stats()
    kv("Chunks indexed", stats["total_chunks"])
    kv("  profile",      n1)
    kv("  competitor",   n2)
    kv("Embedding dim",  stats["embedding_dim"])

    queries = [
        "multi-agent systems and LangGraph orchestration",
        "RAG pipeline production architecture and chunking",
        "LLM cost optimisation and prompt caching strategies",
    ]
    print(f"\n    {DIM}Semantic retrieval test queries:{RESET}")
    for q in queries:
        results = rag.retrieve_context(q, top_k=2)
        assert_non_empty(results, f"RAG results for '{q}'")
        print(f"\n    {CYAN}Query:{RESET} {q!r}")
        for r in results:
            print(f"      {GREEN}[{r.score:.3f}]{RESET}  {DIM}({r.source} / {r.section}){RESET}")
            print(f"      {r.text[:110]}...")

    log_ok("RAG Pipeline", f"chunks={stats['total_chunks']}  queries=3")
    return rag


# ── Step 4: Content Calendar ──────────────────────────────────────────────────

async def step4_calendar(profile_report: dict, competitor_report: dict) -> tuple[Any, str]:
    from orchestrator.calendar_orchestrator import CalendarOrchestrator

    log_step("Step 4 of 8  —  Content Calendar  (14-day schedule)")
    orch = CalendarOrchestrator()
    session = await orch.generate(
        profile_report=profile_report,
        competitor_report=competitor_report,
        start_date="2024-04-01",
        days=14,
    )

    assert session.session_id, "No session_id returned"
    assert len(session.calendar) == 14, f"Expected 14 entries, got {len(session.calendar)}"
    for entry in session.calendar:
        assert_keys(entry, ["day", "date", "platform", "format", "time", "topic"], "calendar_entry")
        assert_non_empty(entry["topic"], f"calendar entry day {entry['day']} topic")

    section("CONTENT CALENDAR  —  14-DAY SCHEDULE", "04")
    kv("Session ID", session.session_id)
    print()
    print(f"    {DIM}{'Day':<5} {'Date':<13} {'Platform':<13} {'Format':<22} {'Time':<8} Topic{RESET}")
    print(f"    {'─' * 78}")
    for e in session.calendar:
        print(
            f"    {WHITE}{e['day']:<5}{RESET}"
            f"{DIM}{e['date']:<13}{RESET}"
            f"{CYAN}{e['platform']:<13}{RESET}"
            f"{e['format']:<22}"
            f"{DIM}{e['time']:<8}{RESET}"
            f"{WHITE}{e['topic']}{RESET}"
        )

    log_ok("Content Calendar", f"session={session.session_id[:8]}...  entries={len(session.calendar)}")
    return orch, session.session_id


# ── Step 5: Human-in-the-Loop Feedback ───────────────────────────────────────

async def step5_hitl(orch: Any, session_id: str) -> None:
    log_step("Step 5 of 8  —  Human-in-the-Loop Calendar Feedback")

    feedbacks = [
        (
            "Replace Day 3 with a deep-dive post about LangGraph state machines",
            "User wants Day 3 to focus on LangGraph internals",
        ),
        (
            "Move long-form content to weekends — keep weekdays short and punchy",
            "User prefers lighter content on weekdays",
        ),
        (
            "Change Day 7 to LinkedIn and use a thought leadership article format",
            "Platform and format override for Day 7",
        ),
    ]

    section("HUMAN-IN-THE-LOOP  —  CALENDAR FEEDBACK", "05")
    for feedback_text, description in feedbacks:
        print(f"\n    {DIM}Scenario: {description}{RESET}")
        print(f"    {BOLD}Input:{RESET}  \"{feedback_text}\"")

        result = orch.feedback(session_id, feedback_text)
        assert "changed" in result, "feedback() must return 'changed' key"
        assert_json_serialisable(result, "feedback_result")

        parsed  = result["parsed"]
        changed = result["changed"]
        print(
            f"    {DIM}Parsed →{RESET}  "
            f"days={parsed['days']}  "
            f"topic={parsed['topic']!r}  "
            f"platform={parsed['platform']}  "
            f"format={parsed['format']}"
        )
        if changed:
            for e in changed:
                print(
                    f"    {GREEN}Updated Day {e['day']:>2}{RESET}  "
                    f"platform={CYAN}{e['platform']}{RESET}  "
                    f"format={e['format']}  "
                    f"topic={WHITE}{e['topic']!r}{RESET}  "
                    f"locked={e['locked']}"
                )
        else:
            log_warn(f"No entries changed: {result.get('unchanged_reason', 'no reason given')}")

    updated = orch.get_calendar(session_id)
    print(f"\n    {DIM}Updated calendar  (★ = modified by feedback):{RESET}")
    print(f"    {DIM}{'Day':<5} {'Platform':<13} {'Format':<22} {'Time':<8} Topic{RESET}")
    print(f"    {'─' * 70}")
    for e in updated:
        flag = f"  {YELLOW}★{RESET}" if e.get("source") == "user_feedback" else ""
        print(
            f"    {e['day']:<5}{CYAN}{e['platform']:<13}{RESET}"
            f"{e['format']:<22}{DIM}{e['time']:<8}{RESET}"
            f"{WHITE}{e['topic']}{RESET}{flag}"
        )

    log_ok("HITL Feedback", f"rounds={len(feedbacks)}")


# ── Step 6: Content Generation ────────────────────────────────────────────────

async def step6_content(profile_report: dict, competitor_report: dict) -> list[dict]:
    from agents.content_context import ContentContext
    from orchestrator.content_creation_orchestrator import ContentCreationOrchestrator

    log_step("Step 6 of 8  —  Content Generation  (3 posts across platforms)")

    tone     = profile_report.get("writing_style", {}).get("tone", "informational")
    keywords = profile_report.get("topics", {}).get("top_keywords", [])[:5]

    contexts = [
        ContentContext(
            topic="building production multi-agent systems with LangGraph",
            tone=tone,
            platform="LinkedIn",
            audience="AI engineers and ML practitioners",
            keywords=keywords,
            brand_voice="technical, precise, and pragmatic",
        ),
        ContentContext(
            topic="RAG pipeline architecture: chunking, re-ranking, and grounding",
            tone="informational",
            platform="Twitter/X",
            audience="ML engineers building LLM applications",
            keywords=["rag", "retrieval", "chunking", "reranking", "grounding"],
        ),
        ContentContext(
            topic="LLM cost optimisation: routing, caching, and batching in production",
            tone="informational",
            platform="Instagram",
            audience="developer advocates and AI startup founders",
            keywords=["llm", "cost", "inference", "caching", "optimisation"],
        ),
    ]

    cc = ContentCreationOrchestrator()
    packages = []

    section("GENERATED CONTENT  —  3 PLATFORM POSTS", "06")
    for i, ctx in enumerate(contexts, 1):
        pkg = await cc.create(ctx)

        assert_non_empty(pkg["post"], f"content[{i}].post")
        assert_non_empty(pkg["hashtags"], f"content[{i}].hashtags")
        assert_non_empty(pkg["visual_prompt"], f"content[{i}].visual_prompt")
        assert isinstance(pkg["hashtags"], list)
        assert_json_serialisable(pkg, f"content[{i}]")

        packages.append(pkg)
        meta = pkg["metadata"]
        print(f"\n    {BOLD}{CYAN}Post {i}  ·  {ctx.platform}  ·  {ctx.tone}{RESET}")
        print(f"    {DIM}Topic: {ctx.topic}{RESET}")
        print(f"    {'─' * 60}")
        print(f"    {BOLD}Copy:{RESET}")
        for line in pkg["post"].split("\n"):
            print(f"      {line}")
        print(f"\n    {BOLD}Hashtags:{RESET}")
        print(f"      {CYAN}{' '.join(pkg['hashtags'])}{RESET}")
        print(f"\n    {BOLD}Visual prompt:{RESET}")
        print(f"      {DIM}{pkg['visual_prompt'][:140]}...{RESET}")
        print(
            f"\n    {DIM}words={meta['word_count']}  tags={meta['hashtag_count']}  "
            f"ratio={meta['aspect_ratio']}  "
            f"copy_src={meta.get('copy_source', 'n/a')}  "
            f"tag_src={meta.get('hashtag_source', 'n/a')}{RESET}"
        )

    log_ok("Content Generation", f"packages={len(packages)}")
    return packages


# ── Step 7: Review System ─────────────────────────────────────────────────────

async def step7_review(db: Any, profile_report: dict) -> list[dict]:
    from agents.content_context import ContentContext
    from services import review_service

    log_step("Step 7 of 8  —  Review System  (create, revise, approve)")

    tone     = profile_report.get("writing_style", {}).get("tone", "informational")
    keywords = profile_report.get("topics", {}).get("top_keywords", [])[:5]

    ctxs = [
        ContentContext(
            topic="LangGraph multi-agent orchestration patterns",
            tone=tone, platform="LinkedIn",
            audience="AI engineers", keywords=keywords,
        ),
        ContentContext(
            topic="production RAG: lessons from 6 months in the wild",
            tone="informational", platform="Twitter/X",
            audience="ML practitioners", keywords=["rag", "retrieval", "production"],
        ),
        ContentContext(
            topic="LLM observability: what to log, trace, and alert on",
            tone="formal", platform="LinkedIn",
            audience="platform engineers and MLOps teams",
            keywords=["observability", "tracing", "llm", "monitoring"],
        ),
    ]

    reviews = []
    for ctx in ctxs:
        r = await review_service.create_review(db, ctx)
        await db.flush()
        assert r["status"] == "pending"
        assert_non_empty(r["post"], f"review #{r['id']} post")
        reviews.append(r)

    section("REVIEW SYSTEM  —  CREATE · REVISE · APPROVE", "07")
    print(f"    {DIM}Created {len(reviews)} reviews  (all status=pending){RESET}\n")

    r1_id             = reviews[0]["id"]
    original_hashtags = reviews[0]["hashtags"]

    print(f"    {BOLD}Action:{RESET}  Rewrite post for review #{r1_id}  {DIM}(CopyAgent only){RESET}")
    updated = await review_service.regenerate(db, r1_id, action="rewrite_post", note="make it more punchy and direct")
    await db.flush()

    assert updated["hashtags"] == original_hashtags, "rewrite_post must NOT change hashtags"
    assert updated["status"] == "revision"
    print(f"    {GREEN}✓  Post rewritten{RESET}  {DIM}hashtags unchanged ✓{RESET}")
    print(f"    {DIM}New copy: {updated['post'][:110]}...{RESET}")

    r2_id            = reviews[1]["id"]
    original_post_r2 = reviews[1]["post"]

    print(f"\n    {BOLD}Action:{RESET}  Regenerate hashtags for review #{r2_id}  {DIM}(HashtagAgent only){RESET}")
    updated2 = await review_service.regenerate(db, r2_id, action="regenerate_hashtags", note="need more niche, technical tags")
    await db.flush()

    assert updated2["post"] == original_post_r2, "regenerate_hashtags must NOT change post text"
    assert isinstance(updated2["hashtags"], list)
    assert_non_empty(updated2["hashtags"], "regenerated hashtags")
    print(f"    {GREEN}✓  Hashtags regenerated{RESET}  {DIM}post text unchanged ✓{RESET}")
    print(f"    {DIM}New tags: {' '.join(updated2['hashtags'][:8])}{RESET}")

    print()
    for r in reviews:
        approved = await review_service.set_status(db, r["id"], "approved", note="LGTM — approved for publishing")
        await db.flush()
        assert approved["status"] == "approved"
        print(f"    {GREEN}✓  Review #{r['id']} approved{RESET}  {DIM}{r['platform']}  ·  {r['topic'][:55]}{RESET}")

    log_ok("Review System", f"reviews={len(reviews)}  rewrite=ok  hashtag_regen=ok  approved=all")
    return reviews


# ── Step 8: Mock Publishing ───────────────────────────────────────────────────

async def step8_publish(db: Any, reviews: list[dict]) -> None:
    from db.review_repository import get as get_review_row
    from services.publish_service import publish as publish_jobs
    from services.metrics import metrics

    log_step("Step 8 of 8  —  Mock Publishing  (per-platform jobs + metrics)")

    platforms   = ["LinkedIn", "Twitter/X", "Instagram"]
    all_results: list[dict] = []

    section("PUBLISH RESULTS  —  PER-PLATFORM JOBS", "08")
    for r in reviews:
        review_row = await get_review_row(db, r["id"])
        assert review_row is not None
        assert review_row.status == "approved"

        results = await publish_jobs(db, review_row, platforms)
        await db.flush()

        assert_non_empty(results, f"publish results for review #{r['id']}")
        assert_json_serialisable(results, f"publish results #{r['id']}")
        all_results.extend(results)

        print(f"\n    {BOLD}Review #{r['id']}{RESET}  {DIM}{r['topic'][:55]}{RESET}")
        for res in results:
            status = res["status"]
            colour = GREEN if status == "posted" else (YELLOW if status == "queued" else RED)
            label  = f"[{status.upper():<6}]"
            url    = res.get("post_url") or res.get("message", "")[:55]
            print(
                f"      {colour}{label}{RESET}  "
                f"{CYAN}{res['platform']:<13}{RESET}"
                f"latency={res.get('latency_ms', 0):.1f}ms   "
                f"{DIM}{url}{RESET}"
            )

    snap = metrics.snapshot()
    g    = snap["global"]
    print(f"\n    {BOLD}Publish Metrics:{RESET}")
    print(
        f"    {DIM}Global{RESET}  "
        f"attempts={g['attempts']}  "
        f"posted={GREEN}{g['success']}{RESET}  "
        f"failed={RED}{g['failed']}{RESET}  "
        f"success_rate={g['success_rate']}%  "
        f"avg_latency={g['avg_latency_ms']}ms"
    )
    for platform, pm in snap["by_platform"].items():
        lats = pm["latency_ms"]
        print(
            f"    {CYAN}{platform:<14}{RESET}"
            f"posted={pm['success']}  failed={pm['failed']}  "
            f"p50={lats['p50']}ms  p95={lats['p95']}ms"
        )

    for res in all_results:
        assert res["status"] in ("posted", "queued", "failed")

    posted = sum(1 for r in all_results if r["status"] == "posted")
    failed = sum(1 for r in all_results if r["status"] == "failed")
    log_ok("Mock Publishing", f"total_jobs={len(all_results)}  posted={posted}  failed={failed}")


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from db.session import Base
    import db.models  # noqa: F401

    _TEST_DB = "sqlite+aiosqlite:///./e2e_test.db"
    _engine  = create_async_engine(_TEST_DB, echo=False)
    _Session = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)

    banner()

    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    t_start = time.perf_counter()
    passed:  list[str]              = []
    failed:  list[tuple[str, str]]  = []

    # ── Load data ─────────────────────────────────────────────────────────
    try:
        my_posts, competitor_posts, _, _ = await load_data()
        passed.append("Data Loading")
    except Exception as exc:
        log_error("Data Loading", str(exc))
        print(f"\n  {RED}Cannot continue without data.{RESET}")
        sys.exit(1)

    async with _Session() as db:
        profile_report    = None
        competitor_report = None
        cal_orch          = None
        cal_session_id    = None
        reviews           = None

        # Run steps sequentially with explicit dep checks
        try:
            profile_report = await step1_profile(my_posts)
            passed.append("Profile Intelligence")
        except Exception as exc:
            log_error("Step 1", str(exc)); failed.append(("Profile Intelligence", str(exc))); traceback.print_exc()

        if profile_report:
            try:
                competitor_report = await step2_competitor(profile_report, competitor_posts)
                passed.append("Competitor Analysis")
            except Exception as exc:
                log_error("Step 2", str(exc)); failed.append(("Competitor Analysis", str(exc))); traceback.print_exc()

        if profile_report and competitor_report:
            try:
                await step3_rag(profile_report, competitor_report)
                passed.append("RAG Pipeline")
            except Exception as exc:
                log_error("Step 3", str(exc)); failed.append(("RAG Pipeline", str(exc))); traceback.print_exc()

        if profile_report and competitor_report:
            try:
                cal_orch, cal_session_id = await step4_calendar(profile_report, competitor_report)
                passed.append("Content Calendar")
            except Exception as exc:
                log_error("Step 4", str(exc)); failed.append(("Content Calendar", str(exc))); traceback.print_exc()

        if cal_orch and cal_session_id:
            try:
                await step5_hitl(cal_orch, cal_session_id)
                passed.append("HITL Feedback")
            except Exception as exc:
                log_error("Step 5", str(exc)); failed.append(("HITL Feedback", str(exc))); traceback.print_exc()

        if profile_report and competitor_report:
            try:
                await step6_content(profile_report, competitor_report)
                passed.append("Content Generation")
            except Exception as exc:
                log_error("Step 6", str(exc)); failed.append(("Content Generation", str(exc))); traceback.print_exc()

        if profile_report:
            try:
                reviews = await step7_review(db, profile_report)
                passed.append("Review System")
            except Exception as exc:
                log_error("Step 7", str(exc)); failed.append(("Review System", str(exc))); traceback.print_exc()

        if reviews:
            try:
                await step8_publish(db, reviews)
                passed.append("Mock Publishing")
            except Exception as exc:
                log_error("Step 8", str(exc)); failed.append(("Mock Publishing", str(exc))); traceback.print_exc()

        try:
            await db.commit()
        except Exception:
            await db.rollback()

    # ── Final report ──────────────────────────────────────────────────────
    elapsed = round(time.perf_counter() - t_start, 1)
    total   = len(passed) + len(failed)

    print(f"\n{BOLD}{CYAN}{'━' * 64}{RESET}")
    print(f"{BOLD}{CYAN}  DEMO COMPLETE  —  FINAL REPORT{RESET}")
    print(f"{BOLD}{CYAN}{'━' * 64}{RESET}")
    kv("Duration",  f"{elapsed}s")
    kv("Steps",     f"{len(passed)}/{total} passed")
    print()
    for name in passed:
        print(f"    {GREEN}✓  {name}{RESET}")
    for name, err in failed:
        print(f"    {RED}✗  {name}  →  {err[:80]}{RESET}")

    if not failed:
        print(f"\n{GREEN}{BOLD}  All steps passed. Pipeline is healthy.{RESET}\n")
        sys.exit(0)
    else:
        print(f"\n{RED}{BOLD}  {len(failed)} step(s) failed. See errors above.{RESET}\n")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
