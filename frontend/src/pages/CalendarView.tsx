import type { PipelineResponse, CalendarEntry } from "../types";
import { Badge } from "../components/ui/Badge";
import { SectionHeader } from "../components/ui/SectionHeader";
import { EmptyState } from "../components/ui/Spinner";

const PLATFORM_BADGE: Record<string, "info" | "indigo" | "warning" | "error" | "default"> = {
  LinkedIn:    "info",
  "Twitter/X": "indigo",
  Instagram:   "warning",
  TikTok:      "default",
  YouTube:     "error",
};

interface Props {
  result: PipelineResponse | null;
}

export default function CalendarView({ result }: Props) {
  if (!result) {
    return <EmptyState icon="📅" message="Run the pipeline first to generate a content calendar." />;
  }

  const calendar: CalendarEntry[] = result.calendar ?? [];

  if (!calendar.length) {
    return (
      <EmptyState
        icon="📭"
        message="No calendar entries in the response. The pipeline ran but calendar data wasn't included."
      />
    );
  }

  const platforms = [...new Set(calendar.map((e) => e.platform))];

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Content Calendar"
        subtitle={`${calendar.length} entries · Session ${result.calendar_session_id?.slice(0, 8)}…`}
        action={
          <div className="flex gap-2">
            {platforms.map((p) => (
              <Badge key={p} variant={PLATFORM_BADGE[p] ?? "default"} dot>
                {p}
              </Badge>
            ))}
          </div>
        }
      />

      <div className="rounded-xl border border-slate-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-900 border-b border-slate-800">
              {["Day", "Date", "Platform", "Format", "Time", "Topic"].map((h) => (
                <th key={h} className="text-left px-4 py-3 text-xs font-medium text-slate-500">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {calendar.map((entry, i) => (
              <tr
                key={entry.day}
                className={`
                  border-b border-slate-800/60 last:border-0
                  transition-colors hover:bg-slate-800/30
                  ${i % 2 === 0 ? "bg-slate-950" : "bg-slate-900/40"}
                `}
              >
                <td className="px-4 py-3">
                  <span className="w-6 h-6 rounded-full bg-slate-800 text-slate-400 text-xs font-semibold flex items-center justify-center">
                    {entry.day}
                  </span>
                </td>
                <td className="px-4 py-3 text-xs text-slate-500">{entry.date}</td>
                <td className="px-4 py-3">
                  <Badge variant={PLATFORM_BADGE[entry.platform] ?? "default"} dot>
                    {entry.platform}
                  </Badge>
                </td>
                <td className="px-4 py-3 text-xs text-slate-400">{entry.format}</td>
                <td className="px-4 py-3 text-xs text-slate-600">{entry.time}</td>
                <td className="px-4 py-3 text-sm font-medium text-slate-200">
                  {entry.topic ?? "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
