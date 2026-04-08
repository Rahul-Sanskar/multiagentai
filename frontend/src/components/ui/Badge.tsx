type BadgeVariant = "default" | "success" | "warning" | "error" | "info" | "indigo";

interface BadgeProps {
  children: React.ReactNode;
  variant?: BadgeVariant;
  dot?: boolean;
}

const STYLES: Record<BadgeVariant, string> = {
  default: "bg-slate-700 text-slate-300 border-slate-600",
  success: "bg-emerald-900/60 text-emerald-400 border-emerald-700/60",
  warning: "bg-amber-900/60 text-amber-400 border-amber-700/60",
  error:   "bg-red-900/60 text-red-400 border-red-700/60",
  info:    "bg-sky-900/60 text-sky-400 border-sky-700/60",
  indigo:  "bg-indigo-900/60 text-indigo-300 border-indigo-700/60",
};

const DOT_COLORS: Record<BadgeVariant, string> = {
  default: "bg-slate-400",
  success: "bg-emerald-400",
  warning: "bg-amber-400",
  error:   "bg-red-400",
  info:    "bg-sky-400",
  indigo:  "bg-indigo-400",
};

export function Badge({ children, variant = "default", dot = false }: BadgeProps) {
  return (
    <span
      className={`
        inline-flex items-center gap-1.5 px-2.5 py-0.5
        text-xs font-medium rounded-full border
        ${STYLES[variant]}
      `}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${DOT_COLORS[variant]}`} />}
      {children}
    </span>
  );
}
