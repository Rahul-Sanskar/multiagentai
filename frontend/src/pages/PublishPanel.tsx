import { useEffect, useState } from "react";
import { getReviews, publishReview, getPublishJobs } from "../services/api";
import type { Review, PublishJob } from "../types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { SectionHeader } from "../components/ui/SectionHeader";
import { LoadingState, EmptyState } from "../components/ui/Spinner";

const PLATFORMS = ["LinkedIn", "Twitter/X", "Instagram"];

const PLATFORM_BADGE: Record<string, "info" | "indigo" | "warning"> = {
  LinkedIn:    "info",
  "Twitter/X": "indigo",
  Instagram:   "warning",
};

const JOB_BADGE: Record<string, "success" | "warning" | "error"> = {
  posted: "success",
  queued: "warning",
  failed: "error",
};

export default function PublishPanel() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [jobs, setJobs] = useState<PublishJob[]>([]);
  const [publishing, setPublishing] = useState<number | null>(null);
  const [selectedPlatforms, setSelectedPlatforms] = useState<Record<number, string[]>>({});
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");

  async function load() {
    setLoading(true);
    try {
      const [r, j] = await Promise.all([getReviews("approved"), getPublishJobs()]);
      setReviews(r); setJobs(j);
    } catch { setError("Failed to load data."); }
    finally { setLoading(false); }
  }

  useEffect(() => { load(); }, []);

  function getPlatformsFor(review: Review): string[] {
    return selectedPlatforms[review.id] ?? [review.platform];
  }

  function togglePlatform(reviewId: number, platform: string) {
    setSelectedPlatforms((prev) => {
      const current = prev[reviewId] ?? [reviews.find((r) => r.id === reviewId)?.platform ?? "LinkedIn"];
      return {
        ...prev,
        [reviewId]: current.includes(platform)
          ? current.filter((p) => p !== platform)
          : [...current, platform],
      };
    });
  }

  async function handlePublish(review: Review) {
    const platforms = getPlatformsFor(review);
    if (!platforms.length) { alert("Select at least one platform."); return; }
    setPublishing(review.id); setError("");
    try {
      const result = await publishReview(review.id, platforms);
      setToast(`Published ${result.published_count}/${result.results.length} jobs`);
      setTimeout(() => setToast(""), 3000);
      await load();
    } catch { setError(`Failed to publish review #${review.id}.`); }
    finally { setPublishing(null); }
  }

  const jobsByReview = jobs.reduce<Record<number, PublishJob[]>>((acc, j) => {
    (acc[j.review_id] ??= []).push(j);
    return acc;
  }, {});

  const totalPosted = jobs.filter((j) => j.status === "posted").length;
  const totalFailed = jobs.filter((j) => j.status === "failed").length;

  return (
    <div className="space-y-5">
      {toast && (
        <div className="fixed top-4 right-4 z-50 px-4 py-3 rounded-xl text-sm font-medium bg-emerald-950 text-emerald-400 border border-emerald-800 shadow-xl shadow-black/40">
          ✓ {toast}
        </div>
      )}

      <SectionHeader
        title="Publish Panel"
        subtitle={`${reviews.length} approved · ${totalPosted} posted · ${totalFailed} failed`}
        action={<Button variant="secondary" size="sm" onClick={load}>↻ Refresh</Button>}
      />

      {jobs.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          <StatTile label="Total jobs" value={jobs.length}   color="text-indigo-400 border-indigo-800/40 bg-indigo-950/30" />
          <StatTile label="Posted"     value={totalPosted}   color="text-emerald-400 border-emerald-800/40 bg-emerald-950/30" />
          <StatTile label="Failed"     value={totalFailed}   color="text-red-400 border-red-800/40 bg-red-950/30" />
        </div>
      )}

      {error && (
        <div className="text-sm rounded-lg px-4 py-3 bg-red-950/60 text-red-400 border border-red-800/60">
          {error}
        </div>
      )}

      {loading ? (
        <LoadingState />
      ) : reviews.length === 0 ? (
        <EmptyState icon="🚀" message="No approved reviews. Go to the Review tab and approve some posts first." />
      ) : (
        <div className="space-y-3">
          {reviews.map((review) => {
            const reviewJobs = jobsByReview[review.id] ?? [];
            const isPublishing = publishing === review.id;
            const activePlatforms = getPlatformsFor(review);

            return (
              <Card
                key={review.id}
                hover
                footer={
                  <Button
                    variant="primary"
                    size="sm"
                    loading={isPublishing}
                    onClick={() => handlePublish(review)}
                  >
                    🚀 Publish
                  </Button>
                }
              >
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <p className="text-sm font-semibold text-slate-100">{review.topic}</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        #{review.id} · {review.platform} · {review.tone}
                      </p>
                    </div>
                    <Badge variant="success" dot>approved</Badge>
                  </div>

                  <p className="text-sm text-slate-400 line-clamp-2">{review.post}</p>

                  <div>
                    <p className="text-xs text-slate-500 mb-2">Publish to</p>
                    <div className="flex gap-2 flex-wrap">
                      {PLATFORMS.map((p) => {
                        const active = activePlatforms.includes(p);
                        return (
                          <button
                            key={p}
                            type="button"
                            onClick={() => togglePlatform(review.id, p)}
                            className={`
                              px-3 py-1.5 text-xs font-medium rounded-lg border transition-all duration-150
                              ${active
                                ? "bg-indigo-600 text-white border-indigo-500"
                                : "bg-slate-800 text-slate-400 border-slate-700 hover:border-slate-500 hover:text-slate-200"
                              }
                            `}
                          >
                            {p}
                          </button>
                        );
                      })}
                    </div>
                  </div>

                  {reviewJobs.length > 0 && (
                    <div className="space-y-1.5">
                      <p className="text-xs text-slate-500">Previous jobs</p>
                      {reviewJobs.map((job) => (
                        <div
                          key={job.id}
                          className="flex items-center gap-3 px-3 py-2 rounded-lg bg-slate-900/60 border border-slate-800 text-xs"
                        >
                          <Badge variant={JOB_BADGE[job.status] ?? "default"} dot>
                            {job.status}
                          </Badge>
                          <span className="text-slate-400">{job.platform}</span>
                          {job.post_url && (
                            <a
                              href={job.post_url}
                              target="_blank"
                              rel="noreferrer"
                              className="ml-auto text-indigo-400 hover:text-indigo-300 hover:underline truncate max-w-xs"
                            >
                              {job.post_url}
                            </a>
                          )}
                          {job.latency_ms && (
                            <span className="text-slate-600 ml-auto">{job.latency_ms.toFixed(0)}ms</span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}

function StatTile({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`rounded-xl px-4 py-3 border flex items-center justify-between ${color}`}>
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-xl font-bold">{value}</span>
    </div>
  );
}
