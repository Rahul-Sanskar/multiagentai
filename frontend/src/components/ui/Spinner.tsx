export function Spinner({ size = "md" }: { size?: "sm" | "md" | "lg" }) {
  const s = { sm: "w-4 h-4", md: "w-5 h-5", lg: "w-7 h-7" }[size];
  return (
    <span
      className={`${s} border-2 border-slate-600 border-t-indigo-400 rounded-full animate-spin inline-block`}
    />
  );
}

export function LoadingState({ message = "Loading…" }: { message?: string }) {
  return (
    <div className="flex items-center justify-center gap-3 py-20 text-slate-500">
      <Spinner />
      <span className="text-sm">{message}</span>
    </div>
  );
}

export function EmptyState({ icon, message }: { icon: string; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-20">
      <span className="text-4xl opacity-25">{icon}</span>
      <p className="text-sm text-slate-500 text-center max-w-sm">{message}</p>
    </div>
  );
}
