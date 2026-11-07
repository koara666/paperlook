import { BookOpenText, Check, ChevronDown, Languages, Library, Monitor, Moon, Settings2, Sparkles, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAiConfig, useDirections, useMeta, useSettings, useUpdateSettings } from "../../api/hooks";
import { LANGUAGES, useLang, useT } from "../../i18n";
import { cn } from "../../lib/cn";
import { Popover, Tooltip } from "../ui/overlay";

function useNav() {
  const t = useT();
  return [
    { to: "/", label: t("nav.today"), icon: Sparkles, end: true },
    { to: "/library", label: t("nav.library"), icon: Library, end: false },
    { to: "/settings", label: t("nav.settings"), icon: Settings2, end: false },
  ];
}

export function Logo({ compact }: { compact?: boolean }) {
  const t = useT();
  return (
    <Link to="/" className="flex min-w-0 items-center gap-2.5">
      <span className="relative flex size-8 shrink-0 items-center justify-center rounded-[10px] bg-accent text-white shadow-soft">
        <BookOpenText className="size-[17px]" strokeWidth={2.2} />
        <span className="absolute -right-0.5 -top-0.5 size-2.5 rounded-full border-2 border-surface bg-[#ffc94d]" />
      </span>
      {!compact && (
        <span className="min-w-0 leading-none">
          <span className="block text-[15px] font-semibold tracking-tight text-text">PaperLook</span>
          <span className="mt-0.5 block truncate text-[11px] text-text-3">{t("app.tagline")}</span>
        </span>
      )}
    </Link>
  );
}

function ThemeToggle() {
  const t = useT();
  const { data } = useSettings();
  const update = useUpdateSettings();
  const mode = data?.reading.theme ?? "system";
  const next = mode === "system" ? "light" : mode === "light" ? "dark" : "system";
  const Icon = mode === "system" ? Monitor : mode === "light" ? Sun : Moon;
  const label = { system: t("theme.system"), light: t("theme.light"), dark: t("theme.dark") }[mode];
  return (
    <Tooltip content={t("theme.tooltip", { mode: label })} side="bottom" align="end">
      <button
        onClick={() => update.mutate({ reading: { ...(data?.reading as any), theme: next } })}
        className="flex size-8 items-center justify-center rounded-lg text-text-3 transition-colors hover:bg-surface-3 hover:text-text"
        aria-label={t("theme.toggle")}
      >
        <Icon className="size-4" />
      </button>
    </Tooltip>
  );
}

/** Language switcher: always visible at the top right, readable whatever the current language is. */
export function LanguageMenu({ compact }: { compact?: boolean }) {
  const { lang, setLang } = useLang();
  const cur = LANGUAGES.find((l) => l.code === lang) ?? LANGUAGES[0];
  return (
    <Popover
      align="end"
      className="w-[200px] p-1.5"
      trigger={({ open, toggle }) => (
        <button
          onClick={toggle}
          aria-label="Language / 语言 / 言語 / 언어"
          title="Language / 语言 / 言語 / 언어"
          className={cn(
            "flex h-8 items-center gap-1.5 rounded-lg px-2 text-[13px] font-medium transition-colors",
            open ? "bg-surface-3 text-text" : "text-text-2 hover:bg-surface-3 hover:text-text",
          )}
        >
          <Languages className="size-4 shrink-0" />
          <span className={cn(compact && "hidden sm:inline")}>{compact ? cur.short : cur.native}</span>
          <ChevronDown className="size-3.5 text-text-3" />
        </button>
      )}
    >
      {(close) => (
        <div role="menu">
          <div className="px-2 pb-1 pt-1 text-[11px] font-medium uppercase tracking-wider text-text-3">Language</div>
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              role="menuitemradio"
              aria-checked={l.code === lang}
              lang={l.locale}
              onClick={() => {
                close();
                setLang(l.code);
              }}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-[13px] transition-colors hover:bg-surface-3",
                l.code === lang ? "font-medium text-text" : "text-text-2",
              )}
            >
              <span className="flex size-4 items-center justify-center">{l.code === lang && <Check className="size-3.5 text-accent" />}</span>
              {l.native}
            </button>
          ))}
        </div>
      )}
    </Popover>
  );
}

function AiStatus() {
  const t = useT();
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
          {data.configured ? (ok ? t("ai.status.ready", { provider: data.label }) : t("ai.status.error", { provider: data.label })) : t("ai.status.none")}
        </span>
        <span className="block truncate text-[11px] text-text-3">{data.configured ? data.model : t("ai.status.add_key")}</span>
      </span>
    </Link>
  );
}

function DirectionList() {
  const t = useT();
  const { data } = useDirections();
  const enabled = (data ?? []).filter((d) => d.enabled);
  if (!enabled.length) return null;
  return (
    <div className="mt-6">
      <div className="mb-1.5 flex items-center justify-between px-2.5">
        <span className="text-[11px] font-medium uppercase tracking-wider text-text-3">{t("nav.directions")}</span>
        <Link to="/settings?s=directions" className="text-[11px] text-text-3 hover:text-accent-text">
          {t("nav.manage")}
        </Link>
      </div>
      <div className="space-y-0.5">
        {enabled.slice(0, 8).map((d) => (
          <Link
            key={d.id}
            to="/settings?s=directions"
            className="flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-[13px] text-text-2 transition-colors hover:bg-surface-3 hover:text-text"
          >
            <span className="size-1.5 shrink-0 rounded-full bg-accent" style={{ opacity: 0.35 + d.weight * 0.13 }} />
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
  const meta = useMeta();
  const nav = useNav();
  return (
    <div className="min-h-screen">
      {/* desktop sidebar */}
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[232px] flex-col border-r border-border bg-surface-2 px-3 py-4 lg:flex">
        <div className="px-2 pb-6 pt-1">
          <Logo />
        </div>
        <nav className="space-y-0.5">
          {nav.map(({ to, label, icon: Icon, end }) => (
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
            <span className="text-[11px] text-text-3">{meta.data ? `v${meta.data.version}` : ""}</span>
            <ThemeToggle />
          </div>
        </div>
      </aside>

      {/* mobile / tablet top bar */}
      <header className="sticky top-0 z-30 flex h-14 items-center justify-between gap-2 border-b border-border bg-surface/90 px-3 backdrop-blur sm:px-4 lg:hidden">
        <div className="min-w-0 flex-1">
          <Logo compact={false} />
        </div>
        <nav className="flex shrink-0 items-center gap-0.5">
          {nav.map(({ to, label, icon: Icon, end }) => (
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
          <LanguageMenu compact />
          <ThemeToggle />
        </nav>
      </header>

      <main className={cn("lg:pl-[232px]", isReader && "")}>
        {/* desktop: utilities at the top right of every page */}
        <div className="hidden h-12 items-center justify-end gap-1 px-6 lg:flex">
          <LanguageMenu />
        </div>
        {children}
      </main>
    </div>
  );
}
