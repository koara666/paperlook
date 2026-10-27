import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from "react";
import { cn } from "../../lib/cn";

// ---------------- Button ----------------
type Variant = "primary" | "secondary" | "ghost" | "soft" | "danger" | "outline";
type Size = "xs" | "sm" | "md" | "lg";

const variants: Record<Variant, string> = {
  primary: "bg-accent text-white hover:bg-accent-hover shadow-soft disabled:opacity-50",
  secondary: "bg-surface text-text border border-border hover:border-border-strong hover:bg-surface-2 shadow-soft disabled:opacity-50",
  outline: "border border-border text-text-2 hover:text-text hover:border-border-strong disabled:opacity-50",
  ghost: "text-text-2 hover:text-text hover:bg-surface-3 disabled:opacity-40",
  soft: "bg-accent-soft text-accent-text hover:brightness-95 dark:hover:brightness-125 disabled:opacity-50",
  danger: "bg-danger-soft text-danger hover:brightness-95 dark:hover:brightness-125 disabled:opacity-50",
};
const sizes: Record<Size, string> = {
  xs: "h-7 px-2 text-xs gap-1 rounded-md",
  sm: "h-8 px-3 text-[13px] gap-1.5 rounded-lg",
  md: "h-9 px-3.5 text-sm gap-2 rounded-lg",
  lg: "h-11 px-5 text-[15px] gap-2 rounded-xl",
};

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = "secondary", size = "md", loading, icon, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center whitespace-nowrap font-medium transition-[background,color,border,box-shadow,filter] duration-150",
        variants[variant],
        sizes[size],
        className,
      )}
      {...rest}
    >
      {loading ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
});

export function IconButton({
  label,
  className,
  children,
  active,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string; active?: boolean }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex size-8 items-center justify-center rounded-lg text-text-3 transition-colors hover:bg-surface-3 hover:text-text disabled:opacity-40",
        active && "text-accent-text",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

// ---------------- Badge ----------------
type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "outline";
const tones: Record<Tone, string> = {
  neutral: "bg-surface-3 text-text-2",
  accent: "bg-accent-soft text-accent-text",
  success: "bg-success-soft text-success",
  warning: "bg-warning-soft text-warning",
  danger: "bg-danger-soft text-danger",
  outline: "border border-border text-text-2",
};

export function Badge({ tone = "neutral", className, children, icon }: { tone?: Tone; className?: string; children: ReactNode; icon?: ReactNode }) {
  return (
    <span className={cn("inline-flex h-[22px] items-center gap-1 whitespace-nowrap rounded-md px-1.5 text-xs font-medium", tones[tone], className)}>
      {icon}
      {children}
    </span>
  );
}

// ---------------- Card ----------------
export function Card({ className, children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("rounded-2xl border border-border bg-surface shadow-soft", className)} {...rest}>
      {children}
    </div>
  );
}

export function SectionTitle({ icon, title, extra, className }: { icon?: ReactNode; title: ReactNode; extra?: ReactNode; className?: string }) {
  return (
    <div className={cn("mb-3 flex items-center justify-between gap-3", className)}>
      <h3 className="flex items-center gap-2 text-[15px] font-semibold text-text">
        {icon && <span className="text-text-3">{icon}</span>}
        {title}
      </h3>
      {extra}
    </div>
  );
}

// ---------------- Switch ----------------
export function Switch({ checked, onChange, disabled, label }: { checked: boolean; onChange: (v: boolean) => void; disabled?: boolean; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-[22px] w-[38px] shrink-0 items-center rounded-full transition-colors duration-200 disabled:opacity-50",
        checked ? "bg-accent" : "bg-border-strong",
      )}
    >
      <span
        className={cn(
          "inline-block size-[18px] rounded-full bg-white shadow-sm transition-transform duration-200",
          checked ? "translate-x-[18px]" : "translate-x-[2px]",
        )}
      />
    </button>
  );
}

// ---------------- Inputs ----------------
export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return (
    <input
      ref={ref}
      className={cn(
        "h-9 w-full rounded-lg border border-border bg-surface px-3 text-sm text-text placeholder:text-text-3 transition-colors focus:border-accent focus:outline-none focus:ring-3 focus:ring-[var(--ring)] disabled:opacity-60",
        className,
      )}
      {...rest}
    />
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return (
    <textarea
      ref={ref}
      className={cn(
        "w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-text placeholder:text-text-3 focus:border-accent focus:outline-none focus:ring-3 focus:ring-[var(--ring)]",
        className,
      )}
      {...rest}
    />
  );
});

export function Field({ label, hint, children, className, extra }: { label: ReactNode; hint?: ReactNode; children: ReactNode; className?: string; extra?: ReactNode }) {
  return (
    <div className={cn("space-y-1.5", className)}>
      <div className="flex items-center justify-between">
        <label className="text-[13px] font-medium text-text">{label}</label>
        {extra}
      </div>
      {children}
      {hint && <p className="text-xs leading-relaxed text-text-3">{hint}</p>}
    </div>
  );
}

// ---------------- Segmented control ----------------
export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  size = "md",
  className,
}: {
  value: T;
  options: { value: T; label: ReactNode; icon?: ReactNode; title?: string }[];
  onChange: (v: T) => void;
  size?: "sm" | "md";
  className?: string;
}) {
  return (
    <div className={cn("inline-flex rounded-lg border border-border bg-surface-3 p-0.5", className)} role="radiogroup">
      {options.map((o) => (
        <button
          key={String(o.value)}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex items-center justify-center gap-1.5 whitespace-nowrap rounded-md font-medium transition-all",
            size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-[13px]",
            o.value === value ? "bg-surface text-text shadow-soft" : "text-text-3 hover:text-text-2",
          )}
        >
          {o.icon}
          {o.label}
        </button>
      ))}
    </div>
  );
}

// ---------------- Progress / loading ----------------
export function ProgressBar({ value, max = 100, indeterminate, className, tone = "accent" }: { value?: number; max?: number; indeterminate?: boolean; className?: string; tone?: "accent" | "success" | "warning" }) {
  const pct = indeterminate ? 40 : Math.max(0, Math.min(100, ((value ?? 0) / (max || 1)) * 100));
  const color = tone === "success" ? "bg-success" : tone === "warning" ? "bg-warning" : "bg-accent";
  return (
    <div className={cn("relative h-1.5 w-full overflow-hidden rounded-full bg-surface-3", className)}>
      <div
        className={cn("absolute inset-y-0 rounded-full transition-[width] duration-500", color)}
        style={indeterminate ? { width: "40%", animation: "indeterminate 1.3s ease-in-out infinite" } : { left: 0, width: `${pct}%` }}
      />
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <Loader2 className={cn("size-4 animate-spin text-text-3", className)} />;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("skeleton rounded-md", className)} />;
}

export function EmptyState({ icon, title, description, action, className }: { icon: ReactNode; title: ReactNode; description?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-col items-center px-6 py-14 text-center", className)}>
      <div className="mb-4 flex size-14 items-center justify-center rounded-2xl bg-accent-soft text-accent-text">{icon}</div>
      <h3 className="text-base font-semibold text-text">{title}</h3>
      {description && <div className="mt-1.5 max-w-md text-sm leading-relaxed text-text-2">{description}</div>}
      {action && <div className="mt-5 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border border-border bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-text-3">{children}</kbd>;
}

export function Notice({ tone = "neutral", icon, title, children, action, className }: { tone?: "neutral" | "warning" | "danger" | "accent" | "success"; icon?: ReactNode; title?: ReactNode; children?: ReactNode; action?: ReactNode; className?: string }) {
  const map = {
    neutral: "border-border bg-surface-2 text-text-2",
    warning: "border-warning/25 bg-warning-soft text-text",
    danger: "border-danger/25 bg-danger-soft text-text",
    accent: "border-accent/20 bg-accent-soft text-text",
    success: "border-success/25 bg-success-soft text-text",
  } as const;
  const iconColor = { neutral: "text-text-3", warning: "text-warning", danger: "text-danger", accent: "text-accent-text", success: "text-success" }[tone];
  return (
    <div className={cn("flex gap-3 rounded-xl border px-4 py-3 text-sm", map[tone], className)}>
      {icon && <div className={cn("mt-0.5 shrink-0", iconColor)}>{icon}</div>}
      <div className="min-w-0 flex-1 leading-relaxed">
        {title && <div className="font-medium text-text">{title}</div>}
        {children && <div className={cn(title && "mt-0.5", "text-text-2")}>{children}</div>}
      </div>
      {action && <div className="shrink-0 self-center">{action}</div>}
    </div>
  );
}
