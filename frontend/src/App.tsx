import { useState } from "react";
import PipelineRunner from "./pages/PipelineRunner";
import CalendarView from "./pages/CalendarView";
import ContentReview from "./pages/ContentReview";
import PublishPanel from "./pages/PublishPanel";
import type { PipelineResponse } from "./types";

const tabs = [
  { id: "Pipeline", icon: "⚡", label: "Pipeline" },
  { id: "Calendar", icon: "📅", label: "Calendar" },
  { id: "Review",   icon: "✍️",  label: "Review" },
  { id: "Publish",  icon: "🚀", label: "Publish" },
] as const;

type Tab = (typeof tabs)[number]["id"];

export default function App() {
  const [tab, setTab] = useState<Tab>("Pipeline");
  const [pipelineResult, setPipelineResult] = useState<PipelineResponse | null>(null);

  return (
    <div className="min-h-screen bg-slate-950">
      <header className="bg-slate-900 border-b border-slate-800 px-6 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-indigo-600 to-purple-600 flex items-center justify-center text-sm font-bold text-white shadow-lg shadow-indigo-900/50">
              AI
            </div>
            <div>
              <h1 className="text-sm font-semibold text-slate-100">
                Social Media Growth Agent
              </h1>
              <p className="text-xs text-slate-500">Autonomous content pipeline</p>
            </div>
          </div>
          <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-950/60 text-emerald-400 border border-emerald-800/60 text-xs font-medium">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
            API connected
          </div>
        </div>
      </header>

      <nav className="bg-slate-900 border-b border-slate-800 px-6">
        <div className="max-w-6xl mx-auto flex gap-1">
          {tabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className={`
                flex items-center gap-2 px-4 py-3 text-sm font-medium
                transition-all duration-150 border-b-2
                ${tab === t.id
                  ? "text-indigo-400 border-indigo-500"
                  : "text-slate-500 border-transparent hover:text-slate-300"
                }
              `}
            >
              <span>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </div>
      </nav>

      <main className="max-w-6xl mx-auto px-6 py-8">
        {tab === "Pipeline" && <PipelineRunner onResult={setPipelineResult} />}
        {tab === "Calendar" && <CalendarView result={pipelineResult} />}
        {tab === "Review"   && <ContentReview />}
        {tab === "Publish"  && <PublishPanel />}
      </main>
    </div>
  );
}
