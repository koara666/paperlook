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
import { cn } from "../lib/cn";
import { clockTime, shortDate, todayHeading } from "../lib/format";

const WINDOWS = [1, 3, 7, 14, 30];
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
  const { data: s } = useSettings();
  const { data: dirs } = useDirections();
  const update = useUpdateSettings();
  const { update: updDir } = useDirectionMutations();
  const [custom, setCustom] = useState("");
  if (!s) return null;
  const enabled = (dirs ?? []).filter((d) => d.enabled);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Popover
        trigger={({ open, toggle }) => (
          <button onClick={toggle}>
            <ControlPill icon={<CalendarRange className="size-4" />} label="时间" value={`近 ${s.window_days} 天`} open={open} />
          </button>
        )}
        className="w-[260px] p-3"
      >
        {(close) => (
          <div>
            <div className="mb-2 text-xs font-medium text-text-3">只推荐这段时间内首次发布的论文</div>
            <div className="grid grid-cols-5 gap-1.5">
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
                  {w}天
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
              <Input value={custom} onChange={(e) => setCustom(e.target.value.replace(/\D/g, ""))} placeholder="自定义天数（1-365）" className="h-8" />
              <Button size="sm" type="submit">
                确定
              </Button>
            </form>
          </div>
        )}
      </Popover>

      <Popover
        trigger={({ open, toggle }) => (
          <button onClick={toggle}>
            <ControlPill icon={<ListOrdered className="size-4" />} label="数量" value={`${s.daily_count} 篇`} open={open} />
          </button>
        )}
        className="w-[240px] p-3"
      >
        {(close) => (
          <div>
            <div className="mb-2 text-xs font-medium text-text-3">每次推荐的论文数量</div>
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
              <span className="text-xs text-text-3">自定义</span>
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
            <ControlPill icon={<Compass className="size-4" />} label="方向" value={enabled.length ? `${enabled.length} 个` : "未设置"} open={open} />
          </button>
        )}
        className="w-[280px] p-1.5"
      >
        <div className="px-2 pb-1.5 pt-1 text-xs font-medium text-text-3">参与本次推荐的研究方向</div>
        <div className="max-h-[280px] overflow-y-auto">
          {(dirs ?? []).map((d) => (
            <button
              key={d.id}
              onClick={() => updDir.mutate({ id: d.id, enabled: !d.enabled })}
              className="flex w-full items-center gap-2.5 rounded-lg px-2 py-2 text-left text-[13px] hover:bg-surface-3"
            >
              <span className={cn("flex size-4 items-center justify-center rounded border", d.enabled ? "border-accent bg-accent text-white" : "border-border-strong")}>
                {d.enabled && <Check className="size-3" strokeWidth={3} />}
              </span>
              <span className="flex-1 truncate text-text">{d.name}</span>
              <span className="text-[11px] text-text-3">{d.keywords.length} 个关键词</span>
            </button>
          ))}
        </div>
        <Link to="/settings?s=directions" className="mt-1 flex items-center gap-2 rounded-lg border-t border-border px-2 py-2 text-[13px] text-accent-text hover:bg-surface-3">
          <Plus className="size-4" />
          添加或编辑研究方向
        </Link>
      </Popover>
    </div>
  );
}

function Onboarding({ onDone }: { onDone: () => void }) {
  const { data: meta } = useMeta();
  const { addPresets } = useDirectionMutations();
  const { data: ai } = useAiConfig();
  const [picked, setPicked] = useState<string[]>([]);
  const toast = useToast();
  return (
    <Card className="overflow-hidden animate-fade-in">
      <div className="border-b border-border bg-gradient-to-br from-accent-soft via-surface to-surface px-6 py-7 sm:px-8">
        <Badge tone="accent" icon={<Sparkles className="size-3" />}>
          欢迎
        </Badge>
        <h2 className="mt-3 text-2xl font-semibold tracking-tight text-text">每天一键，读到与你相关的新论文</h2>
        <p className="mt-2 max-w-2xl text-[15px] leading-relaxed text-text-2">
          PaperLook 会从 arXiv、OpenAlex 等可信来源检索最近发布的论文，按研究相关度、论文质量和时效挑选出最值得读的几篇。
          翻译、总结、模块分析等 AI 功能只会在你点击按钮时运行。
        </p>
      </div>
      <div className="space-y-6 px-6 py-6 sm:px-8">
        <div>
          <div className="mb-3 flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-full bg-accent text-xs font-semibold text-white">1</span>
            <h3 className="font-semibold text-text">选择你的研究方向</h3>
            <span className="text-[13px] text-text-3">可多选，之后随时修改</span>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {meta?.direction_presets.map((p) => {
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
                    <span className="block text-xs text-text-3">{p.name_en}</span>
                    <span className="mt-1 block truncate text-xs text-text-3">{p.keywords.slice(0, 4).join(" · ")}</span>
                  </span>
                </button>
              );
            })}
          </div>
          <Link to="/settings?s=directions&new=1" className="mt-3 inline-flex items-center gap-1.5 text-[13px] text-accent-text hover:underline">
            <Plus className="size-3.5" /> 我的方向不在列表里，自定义一个
          </Link>
        </div>

        <div>
          <div className="mb-2 flex items-center gap-2">
            <span className="flex size-6 items-center justify-center rounded-full bg-surface-3 text-xs font-semibold text-text-2">2</span>
            <h3 className="font-semibold text-text">配置 AI 服务（可选）</h3>
          </div>
          <p className="pl-8 text-[13px] leading-relaxed text-text-2">
            {ai?.configured ? (
              <span className="text-success">✓ 已配置 {ai.label} API Key，AI 功能可用。</span>
            ) : (
              <>
                全文翻译、论文总结等 AI 功能需要 DeepSeek（付费，很便宜）或 Gemini（有免费额度）的 API Key。论文推荐本身不需要，
                <Link to="/settings?s=ai" className="text-accent-text hover:underline">
                  现在配置
                </Link>
                或稍后再说。
              </>
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
                onError: (e) => toast({ tone: "error", title: "保存失败", description: errorMessage(e) }),
              })
            }
          >
            保存并获取今日推荐
          </Button>
          <span className="text-[13px] text-text-3">{picked.length ? `已选择 ${picked.length} 个方向` : "请至少选择一个方向"}</span>
        </div>
      </div>
    </Card>
  );
}

function RunProgress({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const steps = ["连接论文来源", "检索候选论文", "评估质量信号", "计算推荐排序"];
  const ratio = job.total ? job.progress / job.total : 0;
  const stepIdx = job.message?.includes("排序") || job.message?.includes("精排") ? 3 : job.message?.includes("质量") ? 2 : job.message?.includes("检索") ? 1 : 0;
  return (
    <Card className="overflow-hidden border-accent/30 animate-fade-in">
      <div className="px-5 py-5">
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="relative flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
              <Sparkles className="size-5 animate-pulse" />
            </span>
            <div>
              <div className="font-semibold text-text">正在为你挑选论文…</div>
              <div className="mt-0.5 text-[13px] text-text-2">{job.message || "准备中"}</div>
            </div>
          </div>
          <Button size="sm" variant="ghost" icon={<Square className="size-3.5" />} onClick={onCancel}>
            停止
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

function BatchNotice({ batch, onWiden }: { batch: Batch; onWiden: (d: number) => void }) {
  const failed = Object.values(batch.stats.sources ?? {}).filter((s) => s.errors?.length);
  const rerank = batch.stats.ai_rerank;
  if (!batch.message && !failed.length && !(rerank && !rerank.used)) return null;
  return (
    <Notice
      tone="warning"
      icon={<AlertTriangle className="size-4" />}
      title={batch.message ?? "部分来源出现问题"}
      action={
        batch.params.window_days < 7 && batch.message?.includes("扩大") ? (
          <Button size="sm" variant="secondary" onClick={() => onWiden(7)}>
            扩大到 7 天
          </Button>
        ) : undefined
      }
    >
      {failed.length > 0 && (
        <ul className="mt-1 space-y-0.5 text-[13px]">
          {failed.map((s) => (
            <li key={s.name}>
              {s.name}：{s.errors[0]}
              {s.fetched > 0 && `（仍获取到 ${s.fetched} 篇）`}
            </li>
          ))}
        </ul>
      )}
      {rerank && !rerank.used && rerank.note && <div className="mt-1 text-[13px]">{rerank.note}</div>}
    </Notice>
  );
}

export default function TodayPage() {
  const today = useToday();
  const settings = useSettings();
  const directions = useDirections();
  const update = useUpdateSettings();
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
      toast({ tone: n ? "success" : "info", title: n ? `已为你推荐 ${n} 篇论文` : "没有找到新的相关论文", description: j.result?.message ?? undefined });
    } else if (j.status === "failed") {
      toast({ tone: "error", title: "推荐失败", description: j.error ?? undefined });
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
      toast({ tone: "error", title: "无法开始推荐", description: errorMessage(e) });
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
    const t = today.data;
    if (autoTried.current || !s || !t || !hasDirections) return;
    autoTried.current = true;
    if (s.auto_fetch_on_open && t.batches.length === 0 && !isActive(t.active_job)) {
      const key = `pl-auto-${t.day}`;
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

  // group items by batch to show "第 N 批" separators when the user asked for more
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

  return (
    <div className="mx-auto max-w-[920px] px-4 pb-20 pt-6 sm:px-6 lg:pt-10">
      {/* header */}
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-[13px] font-medium text-text-3">{weekday}</div>
          <h1 className="mt-0.5 text-[28px] font-semibold tracking-tight text-text">{date} · 今日推荐</h1>
          {items.length > 0 ? (
            <p className="mt-1 text-sm text-text-2">
              共 {items.length} 篇
              {readCount > 0 && `，已读 ${readCount} 篇`}
              {dirNames.length > 0 && ` · ${dirNames.slice(0, 3).join("、")}${dirNames.length > 3 ? " 等" : ""}`}
            </p>
          ) : (
            <p className="mt-1 text-sm text-text-2">根据你的研究方向，从最近发布的论文中挑选最值得读的几篇。</p>
          )}
        </div>
        {hasDirections && items.length > 0 && (
          <div className="flex items-center gap-2">
            <Tooltip side="bottom" content="重新检索各来源（忽略 2 小时内的检索缓存）">
              <Button variant="ghost" size="md" icon={<RefreshCw className="size-4" />} disabled={running} onClick={() => run("more", true)} aria-label="重新检索" />
            </Tooltip>
            <Button variant="secondary" icon={<Plus className="size-4" />} loading={running} onClick={() => run("more")}>
              再推荐几篇
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
              <Tooltip align="end" content="已开启 AI 精排：每次获取推荐会调用一次 AI（约 1-2 万 tokens）。可在设置中关闭。">
                <Badge tone="accent" icon={<Wand2 className="size-3" />}>
                  AI 精排已开启
                </Badge>
              </Tooltip>
            )}
          </div>

          <div className="space-y-4">
            {running && job.data && <RunProgress job={job.data} onCancel={() => api.post(`/jobs/${job.data!.id}/cancel`)} />}
            {running && !job.data && <Skeleton className="h-28 rounded-2xl" />}

            {!running && batches[0] && <BatchNotice batch={batches[0]} onWiden={(d) => update.mutate({ window_days: d }, { onSuccess: () => run("more") })} />}

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
                  title={hasDirections ? "今天的论文还没有生成" : "没有启用的研究方向"}
                  description={
                    hasDirections ? (
                      <>
                        将从{(settings.data && Object.entries(settings.data.sources).filter(([, v]) => v).length) || ""}个论文来源检索最近 {settings.data?.window_days} 天与
                        「{dirNames.slice(0, 3).join("、")}」相关的新论文，挑选 {settings.data?.daily_count} 篇。
                        <span className="mt-1 block text-text-3">检索与排序不消耗 AI 额度{aiRerank ? "（AI 精排除外）" : ""}。</span>
                      </>
                    ) : (
                      "请在上方「方向」中启用至少一个研究方向。"
                    )
                  }
                  action={
                    hasDirections ? (
                      <Button variant="primary" size="lg" icon={<Sparkles className="size-4" />} onClick={() => run("today")} loading={starting}>
                        获取今日推荐
                      </Button>
                    ) : (
                      <Button variant="secondary" onClick={() => navigate("/settings?s=directions")}>
                        管理研究方向
                      </Button>
                    )
                  }
                />
                {lastBatch && lastBatch.day !== today.data?.day && (
                  <div className="border-t border-border px-6 py-3 text-center text-[13px] text-text-3">
                    上次推荐：{shortDate(lastBatch.day)}
                    <Link to="/library" className="ml-2 inline-flex items-center gap-1 text-accent-text hover:underline">
                      在论文库中查看 <ArrowRight className="size-3" />
                    </Link>
                  </div>
                )}
              </Card>
            ) : (
              groups.map((g, gi) => (
                <div key={g.batch?.id ?? gi} className="space-y-4">
                  {groups.length > 1 && g.batch && (
                    <div className="flex items-center gap-3 pt-2 text-xs text-text-3">
                      <span>{gi === 0 ? "最新" : `第 ${groups.length - gi} 批`} · {clockTime(g.batch.created_at)}</span>
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
  const { data } = useAiConfig();
  if (!data || data.configured) return null;
  return (
    <Notice
      className="mt-6"
      tone="accent"
      icon={<KeyRound className="size-4" />}
      title="想要全文翻译和 AI 精读？"
      action={
        <Link to="/settings?s=ai">
          <Button size="sm" variant="primary">
            配置 AI 服务
          </Button>
        </Link>
      }
    >
      填写 DeepSeek 或 Gemini 的 API Key 后，即可在论文详情页一键翻译全文、生成总结、分析关键模块与创新点。Gemini 有免费额度（需要代理）。
    </Notice>
  );
}
