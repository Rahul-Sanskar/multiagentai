import type { ReactNode, ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "success" | "danger" | "ghost";
type Size    = "sm" | "md";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
}

const VARIANTS: Record<Variant, string> = {
  primary:   "bg-indigo-600 text-white hover:bg-indigo-500 shadow-sm hover:shadow-md active:scale-[0.98]",
  secondary: "bg-slate-700 text-slate-200 border border-slate-600 hover:bg-slate-600 hover:border-slate-500 active:scale-[0.98]",
  success:   "bg-emerald-700 text-white hover:bg-emerald-600 shadow-sm hover:shadow-md active:scale-[0.98]",
  danger:    "bg-red-700/80 text-white hover:bg-red-600 active:scale-[0.98]",
  ghost:     "text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 active:scale-[0.98]",
};

const SIZES: Record<Size, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      disabled={disabled || loading}
      className={`
        inline-flex items-center gap-2 font-medium rounded-lg
        transition-all duration-150
        disabled:opacity-50 disabled:cursor-not-allowed disabled:transform-none
        ${VARIANTS[variant]}
        ${SIZES[size]}
        ${className}
      `}
      {...props}
    >
      {loading && (
        <span className="w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" />
      )}
      {children}
    </button>
  );
}
