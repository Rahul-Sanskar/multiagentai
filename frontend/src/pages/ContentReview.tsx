import { useEffect, useState } from "react";
import { getReviews, approveReview, regenerateField } from "../services/api";
import type { Review } from "../types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { SectionHeader } from "../components/ui/SectionHeader";
import { LoadingState, EmptyState } from "../components/ui/Spinner";

const FILTERS = ["all", "pending", "approved", "revision"] as const;

const STATUS_BADGE: Record<string, "warning" | "success" | "info"> = {
  pending:  "warning",
  approved: "success",
  revision: "info",
};

export default function ContentReview() {
  const [reviews, setReviews] = useState<Review[]>([]);
  const [filter, setFilter] = useState<string>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function load() {
    setLoading(true); setError("");
    try {
      setReviews(await getReviews(filter === "all" ? undefined : filter));
    } catch {
      setError("Failed to load reviews.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, [filter]);

  async function handleApprove(id: number) {
    try {
      const updated = await approveReview(id);
      setReviews((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch { alert("Failed to approve."); }
  }

  async function handleRegenerate(id: number, action: "rewrite_post" | "regenerate_hashtags" | "regenerate_visual") {
    try {
      const updated = await regenerateField(id, action);
      setReviews((prev) => prev.map((r) => (r.id === id ? updated : r)));
    } catch { alert("Regeneration failed."); }
  }

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Content Reviews"
        subtitle={`${reviews.length} ${filter === "all" ? "total" : filter} reviews`}
        action={
          <div className="flex items-center gap-2">
            <div className="flex rounded-lg overflow-hidden border border-slate-700">
              {FILTERS.map((s) => (
                <button
                  key={s}
                  onClick={() => setFilter(s)}
                  className={`
                    px-3 py-1.5 text-xs font-medium capitalize transition-colors
                    ${filter === s ? "bg-indigo-600 text-white" : "bg-slate-800 text-slate-400 hover:text-slate-200"}
                  `}
                >
                  {s}
                </button>
              ))}
            </div>
            <Button variant="secondary" size="sm" onClick={load}>↻ Refresh</Button>
          </div>
        }
      />

      {error && (
        <div className="text-sm rounded-lg px-4 py-3 bg-red-950/60 text-red-400 border border-red-800/60">
          {error}
        </div>
      )}

      {loading ? (
        <LoadingState message="Loading reviews…" />
      ) : reviews.length === 0 ? (
        <EmptyState icon="✍️" message="No reviews found. Run the pipeline to generate content." />
      ) : (
        <div className="space-y-3">
          {reviews.map((r) => (
            <ReviewCard key={r.id} review={r} onApprove={handleApprove} onRegenerate={handleRegenerate} />
          ))}
        </div>
      )}
    </div>
  );
}

interface CardProps {
  review: Review;
  onApprove: (id: number) => void;
  onRegenerate: (id: number, action: "rewrite_post" | "regenerate_hashtags" | "regenerate_visual") => void;
}

function ReviewCard({ review, onApprove, onRegenerate }: CardProps) {
  const [expanded, setExpanded] = useState(false);
  const [regenerating, setRegenerating] = useState<string | null>(null);

  async function regen(action: "rewrite_post" | "regenerate_hashtags" | "regenerate_visual") {
    setRegenerating(action);
    await onRegenerate(review.id, action);
    setRegenerating(null);
  }

  const actions = [
    { action: "rewrite_post"        as const, label: "Rewrite copy" },
    { action: "regenerate_hashtags" as const, label: "New hashtags" },
    { action: "regenerate_visual"   as const, label: "New visual" },
  ];

  return (
    <Card
      hover
      footer={
        <div className="flex items-center gap-2 flex-wrap">
          {review.status !== "approved" && (
            <Button variant="success" size="sm" onClick={() => onApprove(review.id)}>
              ✓ Approve
            </Button>
          )}
          {actions.map(({ action, label }) => (
            <Button
              key={action}
              variant="secondary"
              size="sm"
              loading={regenerating === action}
              onClick={() => regen(action)}
            >
              {label}
            </Button>
          ))}
        </div>
      }
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0 space-y-2">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-semibold text-slate-100 truncate">
              {review.topic}
            </span>
            <Badge variant={STATUS_BADGE[review.status] ?? "default"}>
              {review.status}
            </Badge>
            <span className="text-xs text-slate-500">{review.platform} · {review.tone}</span>
          </div>
          <p className="text-sm text-slate-400 line-clamp-2">{review.post}</p>
        </div>
        <Button variant="ghost" size="sm" onClick={() => setExpanded((v) => !v)}>
          {expanded ? "▲" : "▼"}
        </Button>
      </div>

      {expanded && (
        <div className="mt-4 pt-4 border-t border-slate-700/60 space-y-4">
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Post copy</p>
            <div className="text-sm rounded-lg p-3 bg-slate-900 text-slate-300 border border-slate-700/60 whitespace-pre-wrap">
              {review.post}
            </div>
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Hashtags</p>
            <div className="flex flex-wrap gap-1.5">
              {review.hashtags.map((h) => (
                <Badge key={h} variant="indigo">{h}</Badge>
              ))}
            </div>
          </div>
          <div>
            <p className="text-xs font-medium text-slate-500 mb-2">Visual prompt</p>
            <p className="text-xs text-slate-500 line-clamp-3">{review.visual_prompt}</p>
          </div>
        </div>
      )}
    </Card>
  );
}
