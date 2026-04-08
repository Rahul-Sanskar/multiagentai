import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  footer?: ReactNode;
}

export function Card({ children, className = "", hover = false, footer }: CardProps) {
  return (
    <div
      className={`
        rounded-xl border border-slate-700/60 bg-slate-800/50
        ${hover ? "transition-all duration-200 hover:border-slate-600 hover:bg-slate-800 hover:-translate-y-0.5 hover:shadow-lg hover:shadow-black/20" : ""}
        ${className}
      `}
    >
      <div className="p-5">{children}</div>
      {footer && (
        <div className="px-5 py-3 border-t border-slate-700/60 bg-slate-900/40 rounded-b-xl">
          {footer}
        </div>
      )}
    </div>
  );
}
