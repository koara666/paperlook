import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowRight,
  CalendarRange,
  Check,
  ChevronDown,
  Compass,
  KeyRound,
  ListOrdered,
  Plus,
  RefreshCw,
  Sparkles,
  Square,
  Wand2,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { isActive, useAiConfig, useDirectionMutations, useDirections, useJob, useMeta, useSettings, useToday, useUpdateSettings } from "../api/hooks";
import type { Batch, Job, RecItem } from "../api/types";
import { PaperCardView } from "../components/papers/PaperCard";
import { Popover, Tooltip, useToast } from "../components/ui/overlay";
import { Badge, Button, Card, EmptyState, Input, Notice, ProgressBar, Skeleton } from "../components/ui/primitives";
import { rich, useLang, useT } from "../i18n";
import { cn } from "../lib/cn";
import { clockTime, list, shortDate, todayHeading } from "../lib/format";

const WINDOWS = [1, 3, 7, 14, 30, 90, 180, 365];
const COUNTS = [3, 5, 8, 10, 15];

function ControlPill({ icon, label, value, open }: { icon: React.ReactNode; label: string; value: string; open: boolean }) {
  return (
    <span
      className={cn(
        "inline-flex h-9 items-center gap-2 rounded-lg border bg-surface px-3 text-[13px] shadow-soft transition-colors",
        open ? "border-accent ring-3 ring-[var(--ring)]" : "border-border hover:border-border-strong",
      )}
    >
      <span className="text-text-3">{icon}</span>
      <span className="text-text-3">{label}</span>
      <span className="font-medium text-text">{value}</span>
      <ChevronDown className="size-3.5 text-text-3" />
    </span>
  );
}

function QuickControls() {
  const t = useT();
  const { data: s } = useSettings();
  const { data: dirs } = useDirections();
  const update = useUpdateSettings();
  const { update: updDir } = useDirectionMutations();
  const [custom, setCustom] = useState("");
  if (!s) return null;
  const enabled = (dirs ?? []).filter((d) => d.enabled);
  const ownWindows = enabled.filter((d) => d.window_days && d.window_days !== s.window_days).length;
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Popover
        trigger={({ open, toggle }) => (
          <button onClick={toggle}>
            <ControlPill icon={<CalendarRange className="size-4" />} label={t("today.ctl.time")} value={t("today.ctl.last_days", { n: s.window_days })} open={open} />
          </button>
        )}
        className="w-[272px] p-3"
      >
        {(close) => (
          <div>
            <div className="mb-2 text-xs font-medium text-text-3">{t("today.ctl.time_help")}</div>
            <div className="grid grid-cols-4 gap-1.5">
              {WINDOWS.map((w) => (
                <button
                  key={w}
                  onClick={() => {
                    update.mutate({ window_days: w });
                    close();
                  }}
                  className={cn(
                    "h-8 rounded-lg text-[13px] font-medium transition-colors",
                    s.window_days === w ? "bg-accent text-white" : "bg-surface-3 text-text-2 hover:text-text",
                  )}
                >
                  {t("today.ctl.days", { n: w })}
                </button>
              ))}
            </div>
            <form
              className="mt-2.5 flex gap-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                const n = parseInt(custom, 10);
                if (n >= 1 && n <= 365) {
                  update.mutate({ window_days: n });
                  setCustom("");
                  close();
                }
              }}
            >
              <Input value={custom} onChange={(e) => setCustom(e.target.value.replace(/\D/g, ""))} placeholder={t("today.ctl.custom_days")} className="h-8" />
              <Button size="sm" type="submit">
                {t("common.ok")}
              </Button>
            </form>
            {ownWindows > 0 && <p className="mt-2 text-[11px] leading-relaxed text-text-3">{t("today.ctl.own_windows", { n: ownWindows })}</p>}
          </div>
        )}
      </Popover>

      <Popover
        trigger={({ open, toggle }) => (
          <button onClick={toggle}>
            <ControlPill icon={<ListOrdered className="size-4" />} label={t("today.ctl.count")} value={t("today.ctl.papers", { n: s.daily_count })} open={open} />
          </button>
        )}
        className="w-[240px] p-3"
      >
        {(close) => (
          <div>
            <div className="mb-2 text-xs font-medium text-text-3">{t("today.ctl.count_help")}</div>
            <div className="grid grid-cols-5 gap-1.5">
              {COUNTS.map((c) => (
                <button
                  key={c}
                  onClick={() => {
                    update.mutate({ daily_count: c });
                    close();
                  }}
                  className={cn(
                    "h-8 rounded-lg text-[13px] font-medium",
                    s.daily_count === c ? "bg-accent text-white" : "bg-surface-3 text-text-2 hover:text-text",
                  )}
                >
                  {c}
                </button>
              ))}
            </div>
            <div className="mt-2.5 flex items-center justify-between rounded-lg bg-surface-2 px-2 py-1.5">
              <span className="text-xs text-text-3">{t("today.ctl.custom")}</span>
              <div className="flex items-center gap-1">
                <button className="size-7 rounded-md text-text-2 hover:bg-surface-3" onClick={() => update.mutate({ daily_count: Math.max(1, s.daily_count - 1) })}>
                  −
                </button>
                <span className="w-7 text-center text-sm font-medium tabular-nums">{s.daily_count}</span>
                <button className="size-7 rounded-md text-text-2 hover:bg-surface-3" onClick={() => update.mutate({ daily_count: Math.min(50, s.daily_count + 1) })}>
                  +
                </button>
              </div>
            </div>
          </div>
        )}
      </Popover>

      <Popover
        trigger={({ open, toggle }) => (
          <button onClick={toggle}>
            <ControlPill
              icon={<Compass className="size-4" />}
              label={t("today.ctl.directions")}
              value={enabled.length ? t("today.ctl.n_directions", { n: enabled.length }) : t("today.ctl.none")}
              open={open}
            />
          </button>
        )}
        className="w-[300px] p-1.5"
      >
        <div className="px-2 pb-1.5 pt-1 text-xs font-medium text-text-3">{t("today.ctl.directions_help")}</div>
        <div className="max-h-[280px] overflow-y-auto">
          {(dirs ?? []).map((d) => (
            <button
              key={d.id}
              onClick={() => updDir.mutate({ id: d.id, enabled: !d.enabled })}
              className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-[13px] hover:bg-surface-3"
            >
              <span className={cn("flex size-4 shrink-0 items-center justify-center rounded border", d.enabled ? "border-accent bg-accent text-white" : "border-border-strong")}>
                {d.enabled && <Check className="size-3" strokeWidth={3} />}
              </span>
              <span className="flex-1 truncate text-text">{d.name}</span>
              <span className="shrink-0 text-[11px] text-text-3">
                {d.window_days ? t("today.ctl.days", { n: d.window_days }) + " · " : ""}
                {t("today.ctl.n_keywords", { n: d.keywords.length })}
              </span>
            </button>
          ))}
        </div>
        <Link to="/settings?s=directions" className="mt-1 flex items-center gap-2 rounded-lg border-t border-border px-2 py-2 text-[13px] text-accent-text hover:bg-surface-3">
          <Plus className="size-4" />
          {t("today.ctl.edit_directions")}
        </Link>
      </Popover>
    </div>
  );
}

function Onboarding({ onDone }: { onDone: () => void }) {
  const t = useT();
  const { data: meta } = useMeta();
  const { addPresets } = useDirectionMutations();
  const { data: ai } = useAiConfig();
  const [picked, setPicked] = useState<string[]>([]);
  const [group, setGroup] = useState("cs");
  const toast = useToast();
  const groups = meta?.preset_groups ?? [];
  const presets = (meta?.direction_presets ?? []).filter((p) => p.group === group);
  const countIn = (g: string) => (meta?.direction_presets ?? []).filter((p) => p.group === g && picked.includes(p.key)).length;
  const { lang } = useLang();
  return (
    <Card className="overflow-hidden animate-fade-in">
      <div className="border-b border-border bg-gradient-to-br from-accent-soft via-surface to-surface px-6 py-7 sm:px-8">
        <Badge tone="accent" icon={<Sparkles className="size-3" />}>
          {t("onb.welcome")}
        </Badge>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight text-text">{t("onb.title")}</h2>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-text-2">{t("onb.intro")}</p>
      </div>
      <div className="space-y-6 px-6 py-6 sm:px-8">
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-full bg-accent text-xs font-semibold text-white">1</span>
            <h3 className="font-semibold text-text">{t("onb.step1")}</h3>
            <span className="text-[13px] text-text-3">{t("onb.step1_hint")}</span>
          </div>
          <div className="-mx-1 mb-3 flex flex-wrap gap-1.5 px-1">
            {groups.map((g) => {
              const n = countIn(g.id);
              return (
                <button
                  key={g.id}
                  onClick={() => setGroup(g.id)}
                  className={cn(
                    "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[13px] font-medium transition-colors",
                    group === g.id ? "border-accent bg-accent-soft text-accent-text" : "border-border text-text-2 hover:border-border-strong hover:text-text",
                  )}
                >
                  {g.name}
                  {n > 0 && <span className="flex size-[18px] items-center justify-center rounded-full bg-accent text-[11px] text-white">{n}</span>}
                </button>
              );
            })}
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {presets.map((p) => {
              const on = picked.includes(p.key);
              return (
                <button
                  key={p.key}
                  onClick={() => setPicked(on ? picked.filter((k) => k !== p.key) : [...picked, p.key])}
                  className={cn(
                    "flex items-start gap-3 rounded-xl border p-3 text-left transition-all",
                    on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-border hover:border-border-strong hover:bg-surface-2",
                  )}
                >
                  <span className={cn("mt-0.5 flex size-[18px] shrink-0 items-center justify-center rounded-md border", on ? "border-accent bg-accent text-white" : "border-border-strong")}>
                    {on && <Check className="size-3" strokeWidth={3} />}
                  </span>
                  <span className="min-w-0">
                    <span className="block text-sm font-medium text-text">{p.name}</span>
                    {lang !== "en" && <span className="block text-xs text-text-3">{p.name_en}</span>}
                    <span className="mt-1 block truncate text-xs text-text-3">{p.keywords.slice(0, 4).join(" · ")}</span>
                  </span>
                </button>
              );
            })}
          </div>
          {group === "humanities" || group === "social" ? (
            <p className="mt-3 text-[12px] leading-relaxed text-text-3">{t("onb.slow_fields")}</p>
          ) : null}
          <Link to="/settings?s=directions&new=1" className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-accent-text hover:underline">
            <Plus className="size-3.5" /> {t("onb.custom")}
          </Link>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-full bg-surface-3 text-xs font-semibold text-text-2">2</span>
            <h3 className="font-semibold text-text">{t("onb.step2")}</h3>
          </div>
          <p className="pl-8 text-[13px] leading-relaxed text-text-2">
            {ai?.configured ? (
              <span className="text-success">✓ {t("onb.ai_ready", { provider: ai.label })}</span>
            ) : (
              rich("onb.ai_hint", {}, {
                a: (s) => (
                  <Link to="/settings?s=ai" className="text-accent-text hover:underline">
                    {s}
                  </Link>
                ),
              })
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3 border-t border-border pt-5">
          <Button
            variant="primary"
            size="lg"
            disabled={!picked.length}
            loading={addPresets.isPending}
            icon={<Sparkles className="size-4" />}
            onClick={() =>
              addPresets.mutate(picked, {
                onSuccess: () => onDone(),
                onError: (e) => toast({ tone: "error", title: t("common.save_failed"), description: errorMessage(e) }),
              })
            }
          >
            {t("onb.save_and_fetch")}
          </Button>
          <span className="text-[13px] text-text-3">{picked.length ? t("onb.picked", { n: picked.length }) : t("onb.pick_one")}</span>
        </div>
      </div>
    </Card>
  );
}

function RunProgress({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const t = useT();
  const steps = [t("today.step.connect"), t("today.step.search"), t("today.step.quality"), t("today.step.rank")];
  const ratio = job.total ? job.progress / job.total : 0;
  // engine.run: one step per (source, direction), then quality signals, then ranking
  const stepIdx = !job.total || job.progress === 0 ? 0 : job.progress < job.total - 2 ? 1 : job.progress < job.total - 1 ? 2 : 3;
  return (
    <Card className="overflow-hidden border-accent/30 animate-fade-in">
      <div className="px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className="relative flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
              <Sparkles className="size-5 animate-pulse" />
            </span>
            <div className="min-w-0">
              <div className="font-semibold text-text">{t("today.running")}</div>
              <div className="mt-0.5 truncate text-[13px] text-text-2">{job.message || t("today.preparing")}</div>
            </div>
          </div>
          <Button size="sm" variant="ghost" icon={<Square className="size-3.5" />} onClick={onCancel}>
            {t("common.stop")}
          </Button>
        </div>
        <ProgressBar className="mt-4" value={ratio * 100} indeterminate={!job.total} />
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {steps.map((s, i) => (
            <div key={s} className={cn("flex items-center gap-1.5 text-xs", i < stepIdx ? "text-success" : i === stepIdx ? "text-text" : "text-text-3")}>
              {i < stepIdx ? <Check className="size-3.5" /> : <span className={cn("size-1.5 rounded-full", i === stepIdx ? "bg-accent" : "bg-border-strong")} />}
              {s}
            </div>
          ))}
        </div>
      </div>
    </Card>
  );
}

function BatchNotice({ batch, onWiden, onDirectionWindow }: { batch: Batch; onWiden: (d: number) => void; onDirectionWindow: (id: number, days: number) => void }) {
  const t = useT();
  const failed = Object.values(batch.stats.sources ?? {}).filter((s) => s.errors?.length);
  const rerank = batch.stats.ai_rerank;
  const hints = batch.stats.hints ?? {};
  const sparse = hints.sparse ?? [];
  if (!batch.message && !failed.length && !(rerank && !rerank.used) && !sparse.length) return null;
  return (
    <Notice
      tone="warning"
      icon={<AlertTriangle className="size-4" />}
      title={batch.message ?? t("today.notice.sources")}
      action={
        hints.widen_to && hints.widen_to > batch.params.window_days && !sparse.length ? (
          <Button size="sm" variant="secondary" onClick={() => onWiden(hints.widen_to!)}>
            {t("today.notice.widen", { n: hints.widen_to })}
          </Button>
        ) : undefined
      }
    >
      {sparse.length > 0 && (
        <div className="mt-1.5 space-y-1.5">
          {sparse.map((d) => (
            <div key={d.id} className="flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px]">
              <span>{t("today.notice.sparse", { name: d.name, n: d.candidates, days: d.window })}</span>
              <Button size="xs" variant="secondary" onClick={() => onDirectionWindow(d.id, d.suggest)}>
                {t("today.notice.sparse_action", { n: d.suggest })}
              </Button>
            </div>
          ))}
          <p className="text-[12px] text-text-3">{t("today.notice.sparse_help")}</p>
        </div>
      )}
      {failed.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-[13px]">
          {failed.map((s) => (
            <li key={s.name}>
              {s.name}: {s.errors[0]}
              {s.fetched > 0 && t("today.notice.still_got", { n: s.fetched })}
              {s.fallback && s.fallback.fetched > 0 && t("today.notice.fallback", { via: s.fallback.via, n: s.fallback.fetched })}
            </li>
          ))}
        </ul>
      )}
      {rerank && !rerank.used && rerank.note && <div className="mt-1 text-[13px]">{rerank.note}</div>}
    </Notice>
  );
}

export default function TodayPage() {
  const t = useT();
  const today = useToday();
  const settings = useSettings();
  const directions = useDirections();
  const update = useUpdateSettings();
  const { update: updDir } = useDirectionMutations();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const [jobId, setJobId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const autoTried = useRef(false);

  const activeJobId = jobId ?? (isActive(today.data?.active_job) ? today.data!.active_job!.id : null);
  const job = useJob(activeJobId, (j) => {
    setJobId(null);
    qc.invalidateQueries({ queryKey: ["today"] });
    qc.invalidateQueries({ queryKey: ["history"] });
    qc.invalidateQueries({ queryKey: ["sources"] });
    if (j.status === "done") {
      const n = j.result?.count ?? 0;
      toast({ tone: n ? "success" : "info", title: n ? t("today.toast.done", { n }) : t("today.toast.none"), description: j.result?.message ?? undefined });
    } else if (j.status === "failed") {
      toast({ tone: "error", title: t("today.toast.failed"), description: j.error ?? undefined });
    }
  });
  const running = isActive(job.data) || starting;

  const run = async (mode: "today" | "more" | "auto" = "today", refresh = false) => {
    setStarting(true);
    try {
      const j = await api.post<Job>("/recommend/run", { mode, refresh });
      setJobId(j.id);
      qc.setQueryData(["job", j.id], j);
    } catch (e) {
      toast({ tone: "error", title: t("today.toast.cannot_start"), description: errorMessage(e) });
    } finally {
      setStarting(false);
    }
  };

  const items: RecItem[] = useMemo(() => (today.data?.items ?? []).filter((i) => !i.paper.state.dismissed), [today.data]);
  const hasDirections = (directions.data ?? []).some((d) => d.enabled);
  const noDirectionsAtAll = directions.data && directions.data.length === 0;

  // Optional: run the free (non-AI) search automatically on the first visit of the day.
  useEffect(() => {
    const s = settings.data;
    const td = today.data;
    if (autoTried.current || !s || !td || !hasDirections) return;
    autoTried.current = true;
    if (s.auto_fetch_on_open && td.batches.length === 0 && !isActive(td.active_job)) {
      const key = `pl-auto-${td.day}`;
      try {
        if (sessionStorage.getItem(key)) return;
        sessionStorage.setItem(key, "1");
      } catch {
        /* ignore */
      }
      run("auto");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settings.data, today.data, hasDirections]);

  const { date, weekday } = todayHeading();
  const dirNames = (directions.data ?? []).filter((d) => d.enabled).map((d) => d.name);
  const batches = today.data?.batches ?? [];
  const lastBatch = today.data?.last_batch;
  const aiRerank = settings.data?.ai_rerank;
  const nSources = settings.data ? Object.values(settings.data.sources).filter(Boolean).length : 0;

  // group items by batch to show separators when the user asked for more
  const groups = useMemo(() => {
    const g: { batch: Batch | undefined; items: RecItem[] }[] = [];
    for (const it of items) {
      const last = g[g.length - 1];
      if (last && last.batch?.id === it.batch_id) last.items.push(it);
      else g.push({ batch: batches.find((b) => b.id === it.batch_id), items: [it] });
    }
    return g;
  }, [items, batches]);

  const readCount = items.filter((i) => i.paper.state.read).length;
  const shownNames = list(dirNames.slice(0, 3)) + (dirNames.length > 3 ? t("common.etc") : "");

  return (
    <div className="mx-auto max-w-[920px] px-4 pb-20 pt-6 sm:px-6 lg:pt-2">
      {/* header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="text-[13px] font-medium text-text-3">{weekday}</div>
          <h1 className="mt-0.5 text-[28px] font-semibold tracking-tight text-text">{t("today.heading", { date })}</h1>
          {items.length > 0 ? (
            <p className="mt-1 text-sm text-text-2">
              {t("today.summary", { n: items.length })}
              {readCount > 0 && t("today.summary_read", { n: readCount })}
              {dirNames.length > 0 && ` · ${shownNames}`}
            </p>
          ) : (
            <p className="mt-1 text-sm text-text-2">{t("today.subtitle")}</p>
          )}
        </div>
        {hasDirections && items.length > 0 && (
          <div className="flex items-center gap-2">
            <Tooltip side="bottom" content={t("today.refresh_tip")}>
              <Button variant="ghost" size="md" icon={<RefreshCw className="size-4" />} disabled={running} onClick={() => run("more", true)} aria-label={t("today.refresh")} />
            </Tooltip>
            <Button variant="secondary" icon={<Plus className="size-4" />} loading={running} onClick={() => run("more")}>
              {t("today.more")}
            </Button>
          </div>
        )}
      </div>

      {noDirectionsAtAll ? (
        <Onboarding onDone={() => run("today")} />
      ) : (
        <>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <QuickControls />
            {aiRerank && (
              <Tooltip align="end" content={t("today.rerank_tip")}>
                <Badge tone="accent" icon={<Wand2 className="size-3" />}>
                  {t("today.rerank_on")}
                </Badge>
              </Tooltip>
            )}
          </div>

          <div className="space-y-4">
            {running && job.data && <RunProgress job={job.data} onCancel={() => api.post(`/jobs/${job.data!.id}/cancel`)} />}
            {running && !job.data && <Skeleton className="h-28 rounded-2xl" />}

            {!running && batches[0] && (
              <BatchNotice
                batch={batches[0]}
                onWiden={(d) => update.mutate({ window_days: d }, { onSuccess: () => run("more") })}
                onDirectionWindow={(id, days) => updDir.mutate({ id, window_days: days }, { onSuccess: () => run("more") })}
              />
            )}

            {today.isLoading ? (
              <div className="space-y-4">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-44 rounded-2xl" />
                ))}
              </div>
            ) : items.length === 0 && !running ? (
              <Card>
                <EmptyState
                  icon={<Sparkles className="size-6" />}
                  title={hasDirections ? t("today.empty.title") : t("today.empty.no_directions")}
                  description={
                    hasDirections ? (
                      <>
                        {t("today.empty.desc", { sources: nSources, days: settings.data?.window_days ?? 7, names: shownNames, n: settings.data?.daily_count ?? 5 })}
                        <span className="mt-1 block text-text-3">{aiRerank ? t("today.empty.free_rerank") : t("today.empty.free")}</span>
                      </>
                    ) : (
                      t("today.empty.enable_one")
                    )
                  }
                  action={
                    hasDirections ? (
                      <Button variant="primary" size="lg" icon={<Sparkles className="size-4" />} onClick={() => run("today")} loading={starting}>
                        {t("today.fetch")}
                      </Button>
                    ) : (
                      <Button variant="secondary" onClick={() => navigate("/settings?s=directions")}>
                        {t("today.manage_directions")}
                      </Button>
                    )
                  }
                />
                {lastBatch && lastBatch.day !== today.data?.day && (
                  <div className="border-t border-border px-6 py-3 text-center text-[13px] text-text-3">
                    {t("today.last_batch", { date: shortDate(lastBatch.day) })}
                    <Link to="/library" className="ml-2 inline-flex items-center gap-1 text-accent-text hover:underline">
                      {t("today.view_in_library")} <ArrowRight className="size-3" />
                    </Link>
                  </div>
                )}
              </Card>
            ) : (
              groups.map((g, gi) => (
                <div key={g.batch?.id ?? gi} className="space-y-4">
                  {groups.length > 1 && g.batch && (
                    <div className="flex items-center gap-3 pt-2 text-xs text-text-3">
                      <span>
                        {gi === 0 ? t("today.batch_latest") : t("today.batch_n", { n: groups.length - gi })} · {clockTime(g.batch.created_at)}
                      </span>
                      <span className="h-px flex-1 bg-border" />
                    </div>
                  )}
                  {g.items.map((it, i) => (
                    <PaperCardView
                      key={it.rec_id}
                      index={i}
                      paper={it.paper}
                      score={it.score}
                      breakdown={it.breakdown}
                      direction={it.direction_name}
                      ai={it.ai}
                      aiStatus={it.ai_status}
                    />
                  ))}
                </div>
              ))
            )}
          </div>

          {!settings.data?.ai_rerank && items.length > 0 && <AiHint />}
        </>
      )}
    </div>
  );
}

function AiHint() {
  const t = useT();
  const { data } = useAiConfig();
  if (!data || data.configured) return null;
  return (
    <Notice
      className="mt-6"
      tone="accent"
      icon={<KeyRound className="size-4" />}
      title={t("today.ai_hint.title")}
      action={
        <Link to="/settings?s=ai">
          <Button size="sm" variant="primary">
            {t("today.ai_hint.action")}
          </Button>
        </Link>
      }
    >
      {t("today.ai_hint.body")}
    </Notice>
  );
}
