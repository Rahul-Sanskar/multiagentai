import { useState } from "react";
import { runPipeline } from "../services/api";
import type { PipelineResponse } from "../types";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { Field, TextInput, Textarea } from "../components/ui/Input";
import { SectionHeader } from "../components/ui/SectionHeader";

const PLATFORMS = ["LinkedIn", "Twitter/X", "Instagram", "TikTok", "YouTube"];

const PLATFORM_COLOR: Record<string, string> = {
  LinkedIn:    "text-sky-400 border-sky-700/60 bg-sky-900/30",
  "Twitter/X": "text-blue-400 border-blue-700/60 bg-blue-900/30",
  Instagram:   "text-pink-400 border-pink-700/60 bg-pink-900/30",
  TikTok:      "text-cyan-400 border-cyan-700/60 bg-cyan-900/30",
  YouTube:     "text-red-400 border-red-700/60 bg-red-900/30",
};

const DEFAULT_MY_POSTS = `Just shipped a multi-agent pipeline using LangGraph.
RAG in production: chunking strategy matters more than the model.
Hot take: most teams fine-tune too early.`;

const DEFAULT_COMPETITOR_POSTS = `LangGraph vs AutoGen: which multi-agent framework wins?
Vector DB shootout: Pinecone vs pgvector at 10M vectors.`;

interface Props {
  onResult: (r: PipelineResponse) => void;
}

export default function PipelineRunner({ onResult }: Props) {
  const [myPosts, setMyPosts] = useState(DEFAULT_MY_POSTS);
  const [competitorPosts, setCompetitorPosts] = useState(DEFAULT_COMPETITOR_POSTS);
  const [xUsername, setXUsername] = useState("");
  const [startDate, setStartDate] = useState("");
  const [days, setDays] = useState(3);
  const [platforms, setPlatforms] = useState<string[]>(["LinkedIn"]);
  const [autoApprove, setAutoApprove] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PipelineResponse | null>(null);
  const [error, setError] = useState("");

  function togglePlatform(p: string) {
    setPlatforms((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    );
  }

  function parsePosts(raw: string) {
    return raw.split("\n").map((l) => l.trim()).filter(Boolean).map((text) => ({ text }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const usingX = xUsername.trim().length > 0;
    if (!usingX && !myPosts.trim()) { setError("Enter your posts or an X username."); return; }
    if (!competitorPosts.trim()) { setError("Competitor posts are required."); return; }
    if (!platforms.length) { setError("Select at least one platform."); return; }

    setLoading(true); setError(""); setResult(null);
    try {
      const data = await runPipeline({
        // Always send manual posts — backend uses them as fallback if X fails
        my_posts: parsePosts(myPosts),
        competitor_posts: parsePosts(competitorPosts),
        x_username: xUsername.trim() || undefined,
        start_date: startDate || undefined,
        days, platforms, auto_approve: autoApprove,
      });
      setResult(data);
      onResult(data);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: unknown }; status?: number }; message?: string };
      const detail = e?.response?.data?.detail;
      setError(
        detail
          ? `Error ${e?.response?.status}: ${typeof detail === "string" ? detail : JSON.stringify(detail)}`
          : `${e?.message ?? "Pipeline failed"} — is the backend running on port 8000?`
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <SectionHeader
        title="Run Pipeline"
        subtitle="Enter one post per line. All 8 stages run end-to-end automatically."
      />

      <Card>
        <form onSubmit={handleSubmit} className="space-y-5">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-3">
              <Field label="Your posts (one per line)">
                <Textarea rows={5} value={myPosts} onChange={(e) => setMyPosts(e.target.value)} placeholder="One post per line…" />
              </Field>
              <div className="flex items-center gap-2">
                <div className="flex-1 h-px bg-slate-700" />
                <span className="text-xs text-slate-500">or fetch from X</span>
                <div className="flex-1 h-px bg-slate-700" />
              </div>
              <Field label="X username" hint="Requires X_BEARER_TOKEN in .env. Overrides posts above.">
                <TextInput
                  type="text"
                  value={xUsername}
                  onChange={(e) => setXUsername(e.target.value)}
                  placeholder="e.g. karpathy (without @)"
                />
              </Field>
            </div>
            <Field label="Competitor posts (one per line)">
              <Textarea rows={6} value={competitorPosts} onChange={(e) => setCompetitorPosts(e.target.value)} placeholder="One post per line…" />
            </Field>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Field label="Start date">
              <TextInput type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
            </Field>
            <Field label="Days (1–14)">
              <TextInput type="number" min={1} max={14} value={days} onChange={(e) => setDays(Number(e.target.value))} />
            </Field>
            <Field label="Platforms">
              <div className="flex flex-wrap gap-2 pt-1">
                {PLATFORMS.map((p) => {
                  const active = platforms.includes(p);
                  return (
                    <button
                      key={p}
                      type="button"
                      onClick={() => togglePlatform(p)}
                      className={`
                        px-2.5 py-1 text-xs font-medium rounded-full border transition-all duration-150
                        ${active ? PLATFORM_COLOR[p] : "text-slate-500 border-slate-700 bg-transparent hover:border-slate-500 hover:text-slate-300"}
                      `}
                    >
                      {p}
                    </button>
                  );
                })}
              </div>
            </Field>
          </div>

          <label className="flex items-center gap-3 cursor-pointer w-fit select-none">
            <button
              type="button"
              role="switch"
              aria-checked={autoApprove}
              onClick={() => setAutoApprove((v) => !v)}
              className={`
                relative w-10 h-5 rounded-full border transition-colors duration-200
                ${autoApprove ? "bg-indigo-600 border-indigo-500" : "bg-slate-800 border-slate-700"}
              `}
            >
              <span
                className={`
                  absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all duration-200
                  ${autoApprove ? "left-[calc(100%-18px)]" : "left-0.5"}
                `}
              />
            </button>
            <span className="text-sm text-slate-400">Auto-approve and publish</span>
          </label>

          {error && (
            <div className="text-sm rounded-lg px-4 py-3 bg-red-950/60 text-red-400 border border-red-800/60">
              {error}
            </div>
          )}

          <Button type="submit" loading={loading} size="md">
            ⚡ Run Pipeline
          </Button>
        </form>
      </Card>

      {result && <PipelineResult result={result} />}
    </div>
  );
}

function PipelineResult({ result }: { result: PipelineResponse }) {
  const allPass = result.stages.every((s) => s.success);

  const sourceLabel: Record<string, string> = {
    real_x_api: "Real X data",
    mock:       "Mock fallback",
    manual:     "Manual posts",
  };
  const sourceVariant: Record<string, "success" | "warning" | "default"> = {
    real_x_api: "success",
    mock:       "warning",
    manual:     "default",
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <h3 className="text-base font-semibold text-slate-200">Pipeline Result</h3>
        <div className="flex items-center gap-2">
          <Badge variant={sourceVariant[result.my_posts_source] ?? "default"} dot>
            {sourceLabel[result.my_posts_source] ?? result.my_posts_source}
          </Badge>
          <Badge variant={allPass ? "success" : "warning"} dot>
            {allPass ? "All stages passed" : "Some stages failed"}
          </Badge>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <StatCard label="Calendar entries" value={result.calendar_entries} variant="indigo" />
        <StatCard label="Reviews created"  value={result.reviews_created}  variant="purple" />
        <StatCard label="Publish jobs"     value={result.publish_jobs}     variant="cyan" />
      </div>

      <Card>
        <p className="text-xs font-medium text-slate-500 mb-3">Stage breakdown</p>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {result.stages.map((s) => (
            <div
              key={s.stage}
              className={`
                flex items-center gap-2.5 px-3 py-2 rounded-lg text-xs border
                ${s.success
                  ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-400"
                  : "bg-red-950/40 border-red-800/40 text-red-400"
                }
              `}
            >
              <span className="font-bold">{s.success ? "✓" : "✗"}</span>
              <span className="capitalize">{s.stage.replace(/_/g, " ")}</span>
              {s.error && (
                <span className="ml-auto truncate text-red-500 max-w-[140px]">
                  {s.error.split(";")[0]}
                </span>
              )}
            </div>
          ))}
        </div>
        {result.rag_stats && (
          <p className="text-xs text-slate-600 mt-3">
            RAG: {result.rag_stats.total_chunks} chunks · {result.rag_stats.embedding_dim}d
          </p>
        )}
      </Card>
    </div>
  );
}

const STAT_COLORS: Record<string, string> = {
  indigo: "text-indigo-400 border-indigo-800/40 bg-indigo-950/40",
  purple: "text-purple-400 border-purple-800/40 bg-purple-950/40",
  cyan:   "text-cyan-400 border-cyan-800/40 bg-cyan-950/40",
};

function StatCard({ label, value, variant }: { label: string; value: number; variant: string }) {
  return (
    <div className={`rounded-xl p-4 border ${STAT_COLORS[variant]}`}>
      <p className="text-xs text-slate-500">{label}</p>
      <p className="text-3xl font-bold mt-1">{value}</p>
    </div>
  );
}
