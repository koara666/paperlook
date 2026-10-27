import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { cn } from "../../lib/cn";
import { Button } from "./primitives";

// ---------------- Dialog ----------------
export function Dialog({
  open,
  onClose,
  title,
  description,
  children,
  footer,
  width = "max-w-lg",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-6">
      <div className="absolute inset-0 bg-black/30 backdrop-blur-[2px] animate-fade-in dark:bg-black/50" onClick={onClose} />
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          "relative flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-2xl border border-border bg-surface shadow-pop animate-pop-in sm:rounded-2xl",
          width,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
          <div>
            <h2 className="text-base font-semibold text-text">{title}</h2>
            {description && <p className="mt-0.5 text-[13px] text-text-2">{description}</p>}
          </div>
          <button onClick={onClose} aria-label="关闭" className="-mr-1 rounded-lg p-1 text-text-3 hover:bg-surface-3 hover:text-text">
            <X className="size-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border bg-surface-2 px-5 py-3">{footer}</div>}
      </div>
    </div>,
    document.body,
  );
}

// ---------------- Confirm (promise based) ----------------
type ConfirmOpts = { title: string; description?: ReactNode; confirmText?: string; danger?: boolean };
const ConfirmCtx = createContext<(o: ConfirmOpts) => Promise<boolean>>(async () => false);

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<(ConfirmOpts & { resolve: (v: boolean) => void }) | null>(null);
  const confirm = useCallback((o: ConfirmOpts) => new Promise<boolean>((resolve) => setState({ ...o, resolve })), []);
  const close = (v: boolean) => {
    state?.resolve(v);
    setState(null);
  };
  return (
    <ConfirmCtx.Provider value={confirm}>
      {children}
      <Dialog
        open={!!state}
        onClose={() => close(false)}
        title={state?.title}
        width="max-w-md"
        footer={
          <>
            <Button variant="ghost" onClick={() => close(false)}>
              取消
            </Button>
            <Button variant={state?.danger ? "danger" : "primary"} onClick={() => close(true)} autoFocus>
              {state?.confirmText ?? "确定"}
            </Button>
          </>
        }
      >
        <div className="text-sm leading-relaxed text-text-2">{state?.description}</div>
      </Dialog>
    </ConfirmCtx.Provider>
  );
}

export const useConfirm = () => useContext(ConfirmCtx);

// ---------------- Toasts ----------------
type Toast = { id: number; tone: "success" | "error" | "info"; title: string; description?: string };
const ToastCtx = createContext<(t: Omit<Toast, "id">) => void>(() => {});

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setToasts((ts) => [...ts.slice(-3), { ...t, id }]);
    setTimeout(() => setToasts((ts) => ts.filter((x) => x.id !== id)), t.tone === "error" ? 7000 : 3800);
  }, []);
  return (
    <ToastCtx.Provider value={push}>
      {children}
      {createPortal(
        <div className="pointer-events-none fixed bottom-4 left-1/2 z-[60] flex w-[min(92vw,420px)] -translate-x-1/2 flex-col gap-2 sm:left-auto sm:right-5 sm:translate-x-0">
          {toasts.map((t) => (
            <div key={t.id} className="pointer-events-auto flex items-start gap-3 rounded-xl border border-border bg-surface px-4 py-3 shadow-pop animate-pop-in">
              {t.tone === "success" ? (
                <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" />
              ) : t.tone === "error" ? (
                <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />
              ) : (
                <Info className="mt-0.5 size-4 shrink-0 text-accent" />
              )}
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-text">{t.title}</div>
                {t.description && <div className="mt-0.5 text-[13px] leading-relaxed text-text-2">{t.description}</div>}
              </div>
              <button className="text-text-3 hover:text-text" onClick={() => setToasts((ts) => ts.filter((x) => x.id !== t.id))} aria-label="关闭">
                <X className="size-3.5" />
              </button>
            </div>
          ))}
        </div>,
        document.body,
      )}
    </ToastCtx.Provider>
  );
}

export const useToast = () => useContext(ToastCtx);

// ---------------- Popover ----------------
export function Popover({
  trigger,
  children,
  align = "start",
  side = "bottom",
  className,
  open: controlled,
  onOpenChange,
}: {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  children: ReactNode | ((close: () => void) => ReactNode);
  align?: "start" | "end" | "center";
  side?: "bottom" | "top";
  className?: string;
  open?: boolean;
  onOpenChange?: (v: boolean) => void;
}) {
  const [inner, setInner] = useState(false);
  const open = controlled ?? inner;
  const setOpen = (v: boolean) => (onOpenChange ? onOpenChange(v) : setInner(v));
  const anchor = useRef<HTMLDivElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (anchor.current?.contains(t) || panel.current?.contains(t)) return;
      setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  });

  // The panel lives in a portal with fixed positioning, so no ancestor (cards with
  // animations / overflow) can clip it or paint over it. Keep it inside the viewport.
  useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    const place = () => {
      const a = anchor.current?.getBoundingClientRect();
      const p = panel.current;
      if (!a || !p) return;
      const pw = p.offsetWidth;
      const ph = p.offsetHeight;
      let left = align === "start" ? a.left : align === "end" ? a.right - pw : a.left + a.width / 2 - pw / 2;
      left = Math.max(8, Math.min(left, window.innerWidth - pw - 8));
      let top = side === "bottom" ? a.bottom + 6 : a.top - ph - 6;
      if (side === "bottom" && top + ph > window.innerHeight - 8 && a.top - ph - 6 > 8) top = a.top - ph - 6;
      if (side === "top" && top < 8) top = a.bottom + 6;
      setPos({ top, left });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, align, side]);

  const close = () => setOpen(false);
  return (
    <div className="relative inline-flex" ref={anchor}>
      {trigger({ open, toggle: () => setOpen(!open) })}
      {open &&
        createPortal(
          <div
            ref={panel}
            style={{ position: "fixed", top: pos?.top ?? 0, left: pos?.left ?? 0, visibility: pos ? "visible" : "hidden" }}
            className={cn("z-50 min-w-[200px] rounded-xl border border-border bg-surface p-1.5 shadow-pop animate-pop-in", className)}
          >
            {typeof children === "function" ? children(close) : children}
          </div>,
          document.body,
        )}
    </div>
  );
}

export function MenuItem({ icon, children, onClick, danger, hint, disabled }: { icon?: ReactNode; children: ReactNode; onClick?: () => void; danger?: boolean; hint?: ReactNode; disabled?: boolean }) {
  return (
    <button
      disabled={disabled}
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] transition-colors disabled:opacity-40",
        danger ? "text-danger hover:bg-danger-soft" : "text-text hover:bg-surface-3",
      )}
    >
      {icon && <span className={cn("shrink-0", danger ? "text-danger" : "text-text-3")}>{icon}</span>}
      <span className="flex-1">{children}</span>
      {hint && <span className="text-xs text-text-3">{hint}</span>}
    </button>
  );
}

// ---------------- Tooltip (hover/focus, CSS only) ----------------
export function Tooltip({ content, children, side = "top", align = "center", className }: { content: ReactNode; children: ReactNode; side?: "top" | "bottom"; align?: "center" | "end"; className?: string }) {
  // display:none until hovered, so hidden tooltips never widen the page (mobile overflow).
  return (
    <span className={cn("group/tt relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute z-50 hidden w-max max-w-[260px] rounded-lg bg-[#1d1c19] px-2.5 py-1.5 text-xs leading-relaxed text-white shadow-pop animate-pop-in group-hover/tt:block group-focus-within/tt:block dark:bg-[#33343b]",
          align === "center" ? "left-1/2 -translate-x-1/2" : "right-0",
          side === "top" ? "bottom-full mb-1.5" : "top-full mt-1.5",
        )}
      >
        {content}
      </span>
    </span>
  );
}
