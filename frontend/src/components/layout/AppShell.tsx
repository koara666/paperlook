import { BookOpenText, Library, Monitor, Moon, Settings2, Sparkles, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAiConfig, useDirections, useSettings, useUpdateSettings } from "../../api/hooks";
import { cn } from "../../lib/cn";
import { Tooltip } from "../ui/overlay";

const NAV = [
  { to: "/", label: "今日推荐", icon: Sparkles, end: true },
  { to: "/library", label: "论文库", icon: Library, end: false },
  { to: "/settings", label: "设置", icon: Settings2, end: false },
];

export function Logo({ compact }: { compact?: boolean }) {
  return (
    <Link to="/" className="flex items-center gap-2.5">
      <span className="relative flex size-8 items-center justify-center rounded-[10px] bg-accent text-white shadow-soft">
        <BookOpenText className="size-[17px]" strokeWidth={2.2} />
        <span className="absolute -right-0.5 -top-0.5 size-2.5 rounded-full border-2 border-surface bg-[#ffc94d]" />
      </span>
      {!compact && (
        <span className="leading-none">
          <span className="block text-[15px] font-semibold tracking-tight text-text">PaperLook</span>
          <span className="mt-0.5 block text-[11px] text-text-3">每日论文 · AI 精读</span>
        </span>
      )}
    </Link>
  );
}

function ThemeToggle() {
  const { data } = useSettings();
  const update = useUpdateSettings();
  const mode = data?.reading.theme ?? "system";
  const next = mode === "system" ? "light" : mode === "light" ? "dark" : "system";
  const Icon = mode === "system" ? Monitor : mode === "light" ? Sun : Moon;
  const label = { system: "跟随系统", light: "浅色", dark: "深色" }[mode];
  return (
    <Tooltip content={`外观：${label}（点击切换）`} side="bottom" align="end">
      <button
        onClick={() => update.mutate({ reading: { ...(data?.reading as any), theme: next } })}
        className="flex size-8 items-center justify-center rounded-lg text-text-3 transition-colors hover:bg-surface-3 hover:text-text"
        aria-label="切换外观"
      >
        <Icon className="size-4" />
      </button>
    </Tooltip>
  );
}

function AiStatus() {
  const { data } = useAiConfig();
  if (!data) return <div className="h-10" />;
  const ok = data.configured && data.last_test?.ok !== false;
  return (
    <Link
      to="/settings?s=ai"
      className="group flex items-center gap-2.5 rounded-xl px-2.5 py-2 transition-colors hover:bg-surface-3"
    >
      <span className={cn("size-2 shrink-0 rounded-full", ok ? "bg-success" : data.configured ? "bg-danger" : "bg-warning")} />
      <span className="min-w-0 flex-1 leading-tight">
        <span className="block truncate text-[13px] font-medium text-text">
          {data.configured ? (ok ? "DeepSeek 已就绪" : "DeepSeek 连接异常") : "AI 功能未配置"}
        </span>
        <span className="block truncate text-[11px] text-text-3">{data.configured ? data.model : "点击填写 API Key"}</span>
      </span>
    </Link>
  );
}

function DirectionList() {
  const { data } = useDirections();
  const enabled = (data ?? []).filter((d) => d.enabled);
  if (!enabled.length) return null;
  return (
    <div className="mt-6">
      <div className="mb-1.5 flex items-center justify-between px-2.5">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-3">研究方向</span>
        <Link to="/settings?s=directions" className="text-[11px] text-text-3 hover:text-accent-text">
          管理
        </Link>
      </div>
      <div className="space-y-0.5">
        {enabled.slice(0, 8).map((d) => (
          <Link
            key={d.id}
            to="/settings?s=directions"
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] text-text-2 transition-colors hover:bg-surface-3 hover:text-text"
          >
            <span className="size-1.5 rounded-full bg-accent" style={{ opacity: 0.35 + d.weight * 0.13 }} />
            <span className="truncate">{d.name}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const loc = useLocation();
  const isReader = loc.pathname.startsWith("/paper/");
  return (
    <div className="min-h-screen">
      {/* desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] flex-col border-r border-border bg-surface-2 px-3 py-4 lg:flex">
        <div className="px-2 pb-6 pt-1">
          <Logo />
        </div>
        <nav className="space-y-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm font-medium transition-colors",
                  isActive ? "bg-surface text-text shadow-soft ring-1 ring-border" : "text-text-2 hover:bg-surface-3 hover:text-text",
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cn("size-[17px]", isActive ? "text-accent" : "text-text-3")} />
                  {label}
                </>
              )}
            </NavLink>
          ))}
        </nav>
        <DirectionList />
        <div className="mt-auto space-y-1 border-t border-border pt-3">
          <AiStatus />
          <div className="flex items-center justify-between px-1.5">
            <span className="text-[11px] text-text-3">v1.0</span>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      {/* mobile / tablet top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-surface/90 px-4 backdrop-blur lg:hidden">
        <Logo compact={false} />
        <nav className="flex items-center gap-0.5">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              aria-label={label}
              className={({ isActive }) =>
                cn(
                  "flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-[13px] font-medium",
                  isActive ? "bg-accent-soft text-accent-text" : "text-text-2 hover:bg-surface-3",
                )
              }
            >
              <Icon className="size-4" />
              <span className="hidden sm:inline">{label}</span>
            </NavLink>
          ))}
          <ThemeToggle />
        </nav>
      </header>

      <main className={cn("lg:pl-[232px]", isReader && "")}>{children}</main>
    </div>
  );
}
