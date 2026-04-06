"""
End-to-end pipeline demo — no server needed.

Stages run in order:
  Profile → Competitor → RAG → Calendar → Content → Review → Publish

Run:
    python examples/run_agents.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db.session import engine, Base, AsyncSessionLocal
from orchestrator.pipeline_orchestrator import PipelineOrchestrator

# ── Sample data ───────────────────────────────────────────────────────────────

MY_POSTS = [
    {"text": "Just launched our new product line! Check it out now — limited time offer.",
     "timestamp": "2024-01-01T09:00:00", "likes": 120, "comments": 15, "shares": 30, "views": 2000},
    {"text": "5 tips to grow your business on social media. Thread below",
     "timestamp": "2024-01-03T11:00:00", "likes": 340, "comments": 42, "shares": 88, "views": 5000},
    {"text": "Behind the scenes of our team building day. Great vibes!",
     "timestamp": "2024-01-05T14:00:00", "likes": 210, "comments": 28, "shares": 12, "views": 3100},
    {"text": "New blog post: How AI is transforming content marketing in 2024.",
     "timestamp": "2024-01-07T10:00:00", "likes": 95, "comments": 9, "shares": 22, "views": 1800},
    {"text": "Poll: What content do you want more of? Video / Articles / Infographics",
     "timestamp": "2024-01-09T08:30:00", "likes": 60, "comments": 55, "shares": 5, "views": 1200},
]

COMPETITOR_POSTS = [
    {"text": "Watch our latest video on AI tools for marketers. Game changer!",
     "timestamp": "2024-01-02T10:00:00", "likes": 500, "comments": 80, "shares": 150,
     "views": 9000, "format": "video"},
    {"text": "Top 10 automation tools every startup needs in 2024. Save this post!",
     "timestamp": "2024-01-04T09:00:00", "likes": 620, "comments": 95, "shares": 200, "views": 11000},
    {"text": "Case study: How we grew organic reach by 300% using short-form video.",
     "timestamp": "2024-01-06T11:00:00", "likes": 430, "comments": 60, "shares": 110,
     "views": 7500, "format": "video"},
    {"text": "Infographic: The anatomy of a viral post. Share with your team!",
     "timestamp": "2024-01-08T08:00:00", "likes": 380, "comments": 45, "shares": 175,
     "views": 6800, "format": "image"},
    {"text": "Exclusive webinar on growth hacking — register now, free seats limited!",
     "timestamp": "2024-01-10T07:00:00", "likes": 290, "comments": 38, "shares": 90, "views": 5200},
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sep(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print('=' * 60)


def _json(obj: object) -> None:
    print(json.dumps(obj, indent=2, default=str))


# ── Main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    # Ensure DB tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    orch = PipelineOrchestrator()

    async with AsyncSessionLocal() as db:
        _sep("RUNNING FULL PIPELINE  (Profile → Competitor → RAG → Calendar → Content → Review → Publish)")

        result = await orch.run(
            my_posts=MY_POSTS,
            competitor_posts=COMPETITOR_POSTS,
            db=db,
            start_date="2024-02-01",
            days=5,                     # keep demo short
            platforms=["Instagram", "LinkedIn"],
            auto_approve=True,          # auto-approve + publish
        )

        await db.commit()

        # ── Stage summary ─────────────────────────────────────────────────
        _sep("STAGE RESULTS")
        print(result.summary())

        # ── Profile report ────────────────────────────────────────────────
        _sep("PROFILE REPORT")
        _json(result.profile_report)

        # ── Competitor report ─────────────────────────────────────────────
        _sep("COMPETITOR REPORT")
        _json(result.competitor_report)

        # ── RAG stats ─────────────────────────────────────────────────────
        _sep("RAG INDEX STATS")
        _json(result.rag_stats)

        # ── Calendar ──────────────────────────────────────────────────────
        _sep(f"CALENDAR  (session={result.calendar_session_id})")
        for e in result.calendar:
            print(f"  Day {e['day']:>2} | {e['date']} | {e['platform']:<12} "
                  f"| {e['format']:<18} | {e['time']} | {e['topic']}")

        # ── Reviews ───────────────────────────────────────────────────────
        _sep(f"REVIEWS  ({len(result.reviews)} created)")
        for r in result.reviews:
            print(f"  #{r['id']:>3} [{r['status']:<8}] {r['platform']:<12} "
                  f"topic={r['topic']!r}")
            print(f"         post    : {r['post'][:80]}...")
            print(f"         hashtags: {r['hashtags'][:4]}")

        # ── Publish results ───────────────────────────────────────────────
        _sep(f"PUBLISH JOBS  ({len(result.publish_results)} total)")
        for p in result.publish_results:
            icon = "posted" if p["status"] == "posted" else ("queued" if p["status"] == "queued" else "FAILED")
            print(f"  [{icon:<6}] {p['platform']:<12} "
                  f"latency={p.get('latency_ms', 0):.1f}ms  "
                  f"url={p.get('post_url') or p.get('message', '')}")

        # ── Metrics ───────────────────────────────────────────────────────
        from services.metrics import metrics
        _sep("PUBLISH METRICS")
        snap = metrics.snapshot()
        g = snap["global"]
        print(f"  Global  attempts={g['attempts']}  success={g['success']}  "
              f"failed={g['failed']}  success_rate={g['success_rate']}%  "
              f"avg_latency={g['avg_latency_ms']}ms")
        for platform, pm in snap["by_platform"].items():
            lats = pm["latency_ms"]
            print(f"  {platform:<12} success={pm['success']}  failed={pm['failed']}  "
                  f"p50={lats['p50']}ms  p95={lats['p95']}ms")


if __name__ == "__main__":
    asyncio.run(main())
