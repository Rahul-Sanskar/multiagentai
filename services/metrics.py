"""
In-memory metrics store for the publish pipeline — with JSON file persistence.

Tracks per-platform:
  - attempt count
  - success / failure / queued counts
  - latency samples (ms)

Exposes:
  record(platform, status, latency_ms)  — thread-safe, auto-saves after each call
  snapshot() -> dict                    — current aggregated view
  reset()                               — clear all metrics (useful in tests)

Persistence:
  Metrics are saved to METRICS_PATH (default: data/metrics.json) after every
  record() call and loaded automatically on first import.
  Set METRICS_PATH = None to disable persistence (e.g. in tests).
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Set to None to disable file persistence (useful in tests)
METRICS_PATH: Path | None = Path("data/metrics.json")


class _PlatformMetrics:
    __slots__ = ("attempts", "success", "failed", "queued", "latencies")

    def __init__(self):
        self.attempts: int = 0
        self.success: int = 0
        self.failed: int = 0
        self.queued: int = 0
        self.latencies: list[float] = []   # ms

    def to_dict(self) -> dict[str, Any]:
        lats = self.latencies
        total = self.attempts or 1
        return {
            "attempts":      self.attempts,
            "success":       self.success,
            "failed":        self.failed,
            "queued":        self.queued,
            "success_rate":  round(self.success / total * 100, 2),
            "failure_rate":  round(self.failed  / total * 100, 2),
            "latency_ms": {
                "count": len(lats),
                "min":   round(min(lats), 2) if lats else 0,
                "max":   round(max(lats), 2) if lats else 0,
                "avg":   round(sum(lats) / len(lats), 2) if lats else 0,
                "p50":   round(_percentile(lats, 50), 2) if lats else 0,
                "p95":   round(_percentile(lats, 95), 2) if lats else 0,
                "p99":   round(_percentile(lats, 99), 2) if lats else 0,
            },
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "_PlatformMetrics":
        """Restore a _PlatformMetrics instance from a serialised dict."""
        m = cls()
        m.attempts  = d.get("attempts", 0)
        m.success   = d.get("success", 0)
        m.failed    = d.get("failed", 0)
        m.queued    = d.get("queued", 0)
        m.latencies = d.get("latencies", [])
        return m


class MetricsStore:
    """
    Thread-safe metrics store with optional JSON file persistence.

    On initialisation the store attempts to load previously saved metrics
    from METRICS_PATH so counters survive process restarts.
    After every record() call the store is flushed to disk (fire-and-forget,
    errors are silently swallowed to never block the publish path).
    """

    def __init__(self, path: Path | None = METRICS_PATH):
        self._lock = threading.Lock()
        self._platforms: dict[str, _PlatformMetrics] = defaultdict(_PlatformMetrics)
        self._global_start: float = time.time()
        self._path = path
        self._load()

    # ── Public API ────────────────────────────────────────────────────────

    def record(self, platform: str, status: str, latency_ms: float) -> None:
        """
        Record one publish attempt and persist metrics to disk.

        Parameters
        ----------
        platform   : e.g. "Instagram"
        status     : "posted" | "failed" | "queued"
        latency_ms : round-trip time in milliseconds
        """
        with self._lock:
            m = self._platforms[platform]
            m.attempts += 1
            m.latencies.append(latency_ms)
            if status == "posted":
                m.success += 1
            elif status == "failed":
                m.failed += 1
            elif status == "queued":
                m.queued += 1
        # Persist outside the lock to minimise contention
        self._save()

    def snapshot(self) -> dict[str, Any]:
        """Return a full metrics snapshot across all platforms."""
        with self._lock:
            platforms = {k: v.to_dict() for k, v in self._platforms.items()}

            all_lats = [lat for m in self._platforms.values() for lat in m.latencies]
            total_attempts = sum(m.attempts for m in self._platforms.values())
            total_success  = sum(m.success  for m in self._platforms.values())
            total_failed   = sum(m.failed   for m in self._platforms.values())
            total_queued   = sum(m.queued   for m in self._platforms.values())

            return {
                "uptime_seconds": round(time.time() - self._global_start, 1),
                "global": {
                    "attempts":     total_attempts,
                    "success":      total_success,
                    "failed":       total_failed,
                    "queued":       total_queued,
                    "success_rate": round(total_success / (total_attempts or 1) * 100, 2),
                    "failure_rate": round(total_failed  / (total_attempts or 1) * 100, 2),
                    "avg_latency_ms": round(
                        sum(all_lats) / len(all_lats), 2
                    ) if all_lats else 0,
                },
                "by_platform": platforms,
            }

    def reset(self) -> None:
        """Clear all metrics and remove the persistence file."""
        with self._lock:
            self._platforms.clear()
            self._global_start = time.time()
        if self._path:
            try:
                self._path.unlink(missing_ok=True)
            except OSError:
                pass

    # ── Persistence ───────────────────────────────────────────────────────

    def _save(self) -> None:
        """
        Serialise current metrics to JSON.
        Called after every record(); errors are silently ignored so the
        publish path is never blocked by a filesystem issue.
        """
        if not self._path:
            return
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._lock:
                payload = {
                    "global_start": self._global_start,
                    "platforms": {
                        k: {**v.to_dict(), "latencies": v.latencies}
                        for k, v in self._platforms.items()
                    },
                }
            self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception:
            pass  # never crash the publish pipeline over a metrics write

    def _load(self) -> None:
        """
        Load previously persisted metrics from disk on startup.
        Missing or corrupt files are silently ignored — the store starts fresh.
        """
        if not self._path or not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            self._global_start = raw.get("global_start", time.time())
            for platform, data in raw.get("platforms", {}).items():
                self._platforms[platform] = _PlatformMetrics.from_dict(data)
        except Exception:
            pass  # corrupt file — start fresh


def _percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (pct / 100) * (len(sorted_data) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (idx - lo)


# Singleton — shared across the process, loads persisted data on import
metrics = MetricsStore()
