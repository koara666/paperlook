import { useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BookA,
  Check,
  ChevronDown,
  ClipboardCopy,
  Download,
  ExternalLink,
  FileWarning,
  Languages,
  ListTree,
  Loader2,
  MoreHorizontal,
  Play,
  RefreshCw,
  RotateCcw,
  Square,
  Type,
} from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { isActive, useAiLabel, useFulltext, useJob, useSettings, useTranslateRequests, useUpdateSettings } from "../../api/hooks";
import type { Block, FullDoc, FulltextResponse, Job, PaperDetail, Section } from "../../api/types";
import { Dialog, MenuItem, Popover, Tooltip, useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, Notice, ProgressBar, Segmented, Skeleton } from "../../components/ui/primitives";
import { cn } from "../../lib/cn";
import { MathBlock, MathText, plainText } from "../../lib/math";
import { estimateTokens, useAiRunner } from "./AiPanel";

type View = "en" | "bilingual" | "zh";
type TMap = Record<string, { text: string; flags: string[] }>;

// ---------------- rendering of document blocks ----------------
const Para = memo(function Para({ orig, zh, view, as = "p", className }: { orig: string; zh?: string; view: View; as?: "p" | "span"; className?: string }) {
  const Tag = as;
  if (view === "en" || (!zh && view === "bilingual")) {
    return (
      <Tag className={cn("orig block text-text", className)}>
        <MathText text={orig} />
      </Tag>
    );
  }
  if (view === "zh") {
    if (!zh)
      return (
        <Tag className={cn("orig block text-text-3", className)}>
          <MathText text={orig} />
          <span className="ml-2 inline-flex rounded bg-surface-3 px-1.5 align-middle font-sans text-[11px] text-text-3">未翻译</span>
        </Tag>
      );
    return (
      <Tag className={cn("zh block text-text", className)}>
        <MathText text={zh} />
      </Tag>
    );
  }
  return (
    <span className={cn("block", className)}>
      <span className="orig block text-[0.93em] text-text-2">
        <MathText text={orig} />
      </span>
      <span className="zh mt-1.5 block border-l-2 border-accent/35 pl-3 text-text">
        <MathText text={zh!} />
      </span>
    </span>
  );
});

function Caption({ label, id, caption, tr, view }: { label: string | null; id: string; caption: string; tr: TMap; view: View }) {
  if (!caption && !label) return null;
  return (
    <figcaption className="mt-2.5 text-[0.86em] leading-relaxed">
      {label && <span className="mr-1.5 font-sans font-semibold text-text">{label}</span>}
      {caption && <Para as="span" orig={caption} zh={tr[`${id}::caption`]?.text} view={view} />}
    </figcaption>
  );
}

const BlockView = memo(function BlockView({ b, tr, view, onImage }: { b: Block; tr: TMap; view: View; onImage: (src: string) => void }) {
  switch (b.type) {
    case "paragraph":
      return <Para orig={b.text} zh={tr[b.id]?.text} view={view} className="my-4" />;
    case "heading":
      return (
        <div className="mb-2 mt-6 font-sans font-semibold">
          <Para orig={b.text} zh={tr[b.id]?.text} view={view} />
        </div>
      );
    case "equation":
      return (
        <div className="my-4 flex items-center gap-3">
          <MathBlock latex={b.latex} className="min-w-0 flex-1 text-text" />
          {b.tag && <span className="shrink-0 font-sans text-sm text-text-3">{b.tag}</span>}
        </div>
      );
    case "list": {
      const L = b.ordered ? "ol" : "ul";
      return (
        <L className={cn("my-4 space-y-2 pl-6", b.ordered ? "list-decimal" : "list-disc", "marker:text-text-3")}>
          {b.items.map((it, i) => (
            <li key={i}>
              <Para as="span" orig={it} zh={tr[`${b.id}::${i}`]?.text} view={view} />
            </li>
          ))}
        </L>
      );
    }
    case "figure":
      return (
        <figure className="my-6 rounded-xl border border-border bg-surface-2 p-3 sm:p-4">
          {b.images.length > 0 ? (
            <div className={cn("grid gap-2", b.images.length > 1 && "sm:grid-cols-2")}>
              {b.images.map((src) => (
                <button key={src} onClick={() => onImage(src)} className="overflow-hidden rounded-lg bg-white" title="点击放大">
                  <img src={src} alt={b.label ?? "figure"} loading="lazy" className="mx-auto max-h-[460px] w-auto object-contain" />
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center font-sans text-xs text-text-3">图片无法从全文中提取，请查看原文 PDF</div>
          )}
          <Caption label={b.label} id={b.id} caption={b.caption} tr={tr} view={view} />
        </figure>
      );
    case "table":
      return (
        <figure className="my-6">
          <Caption label={b.label} id={b.id} caption={b.caption} tr={tr} view={view} />
          {b.tables.map((rows, ti) => (
            <div key={ti} className="mt-2.5 overflow-x-auto rounded-xl border border-border">
              <table className="w-full border-collapse font-sans text-[13px]">
                <tbody>
                  {rows.map((row, ri) => (
                    <tr key={ri} className={cn(ri === 0 && "bg-surface-2", "border-b border-border last:border-0")}>
                      {row.map((cell, ci) => {
                        const C = cell.h || ri === 0 ? "th" : "td";
                        return (
                          <C
                            key={ci}
                            colSpan={cell.cs}
                            rowSpan={cell.rs}
                            className={cn("whitespace-nowrap px-3 py-1.5 text-center text-text", (cell.b || C === "th") && "font-semibold")}
                          >
                            <MathText text={cell.t} />
                          </C>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}
          {b.text && <pre className="mt-2 overflow-x-auto rounded-lg bg-surface-2 p-3 font-mono text-xs">{b.text}</pre>}
        </figure>
      );
    case "code":
      return (
        <figure className="my-6">
          {(b.label || b.caption) && <Caption label={b.label} id={b.id} caption={b.caption} tr={tr} view={view} />}
          {b.text && (
            <pre className="mt-2 overflow-x-auto rounded-xl border border-border bg-surface-2 p-4 font-mono text-[12.5px] leading-relaxed text-text">
              {b.text.split("\n").map((ln, i) => (
                <div key={i}>
                  <MathText text={ln} />
                </div>
              ))}
            </pre>
          )}
        </figure>
      );
    case "unparsed":
      return (
        <div className="my-4 rounded-lg border border-dashed border-border bg-surface-2 px-3 py-2">
          <div className="font-mono text-[13px] text-text-2">{b.text}</div>
          <div className="mt-1 font-sans text-[11px] text-warning">{b.note}</div>
        </div>
      );
    default:
      return null;
  }
});

function SectionView({
  s,
  tr,
  view,
  done,
  total,
  onImage,
  onRetranslate,
  canTranslate,
}: {
  s: Section;
  tr: TMap;
  view: View;
  done: number;
  total: number;
  onImage: (src: string) => void;
  onRetranslate: (sid: string) => void;
  canTranslate: boolean;
}) {
  const toast = useToast();
  const H = s.level === 1 ? "h2" : s.level === 2 ? "h3" : "h4";
  const titleZh = tr[`${s.id}::title`]?.text;
  const copy = async () => {
    const parts: string[] = [];
    for (const b of s.blocks) {
      if (b.type === "paragraph" || b.type === "heading") parts.push(tr[b.id]?.text ?? b.text);
      if (b.type === "list") b.items.forEach((it, i) => parts.push("• " + (tr[`${b.id}::${i}`]?.text ?? it)));
    }
    try {
      await navigator.clipboard.writeText(plainText(`${titleZh ?? s.title}\n\n${parts.join("\n\n")}`));
      toast({ tone: "success", title: "已复制本节内容" });
    } catch {
      toast({ tone: "error", title: "复制失败", description: "浏览器不允许访问剪贴板" });
    }
  };
  return (
    <section id={`sec-${s.id}`} data-sid={s.id} className="scroll-mt-36">
      <div className={cn("group flex items-start gap-2", s.level === 1 ? "mb-2 mt-12" : "mb-1 mt-9")}>
        <H className={cn("min-w-0 flex-1 font-sans font-semibold tracking-tight text-text", s.level === 1 ? "text-[1.35em]" : s.level === 2 ? "text-[1.15em]" : "text-[1.02em]")}>
          {s.number && <span className="mr-2 text-text-3">{s.number}</span>}
          {view !== "en" && titleZh ? titleZh : <MathText text={s.title} />}
          {view === "bilingual" && titleZh && (
            <span className="ml-2 font-serif text-[0.75em] font-normal text-text-3">
              <MathText text={s.title} />
            </span>
          )}
        </H>
        <div className="flex shrink-0 items-center gap-0.5 pt-1 opacity-0 transition-opacity group-hover:opacity-100 max-sm:opacity-100">
          {total > 0 && done > 0 && done < total && <span className="mr-1 text-[11px] text-text-3">{done}/{total}</span>}
          <Tooltip content="复制本节（优先复制译文）" align="end">
            <button onClick={copy} className="rounded-md p-1.5 text-text-3 hover:bg-surface-3 hover:text-text" aria-label="复制本节">
              <ClipboardCopy className="size-3.5" />
            </button>
          </Tooltip>
          {canTranslate && total > 0 && (
            <Tooltip content={done ? "重新翻译本节" : "翻译本节"} align="end">
              <button onClick={() => onRetranslate(s.id)} className="rounded-md p-1.5 text-text-3 hover:bg-surface-3 hover:text-text" aria-label="翻译本节">
                <RotateCcw className="size-3.5" />
              </button>
            </Tooltip>
          )}
        </div>
      </div>
      {s.blocks.map((b) => (
        <BlockView key={b.id} b={b} tr={tr} view={view} onImage={onImage} />
      ))}
    </section>
  );
}

function References({ sections }: { sections: Section[] }) {
  const [open, setOpen] = useState(false);
  const refs = sections.flatMap((s) => s.blocks.filter((b) => b.type === "reference")) as Extract<Block, { type: "reference" }>[];
  if (!refs.length) return null;
  return (
    <div className="mt-14 rounded-xl border border-border font-sans">
      <button onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-4 py-3 text-left">
        <span className="text-[15px] font-semibold text-text">
          参考文献 <span className="font-normal text-text-3">（{refs.length}，保留原文不翻译）</span>
        </span>
        <ChevronDown className={cn("size-4 text-text-3 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <ol className="space-y-2 border-t border-border px-4 py-3 text-[13px] leading-relaxed text-text-2">
          {refs.map((r) => (
            <li key={r.id} className="flex gap-2">
              {r.label && <span className="shrink-0 text-text-3">{r.label}</span>}
              <span>
                <MathText text={r.text} />
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function Toc({ doc, tr, view, status, active }: { doc: FullDoc; tr: TMap; view: View; status: FulltextResponse["translation_status"]; active: string | null }) {
  return (
    <nav className="space-y-0.5 text-[13px]">
      {doc.sections
        .filter((s) => s.kind !== "references")
        .map((s) => {
          const st = status?.sections[s.id];
          const full = st && st.total > 0 && st.done >= st.total;
          const part = st && st.done > 0 && !full;
          const title = view !== "en" ? tr[`${s.id}::title`]?.text ?? plainText(s.title) : plainText(s.title);
          return (
            <a
              key={s.id}
              href={`#sec-${s.id}`}
              onClick={(e) => {
                e.preventDefault();
                document.getElementById(`sec-${s.id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className={cn(
                "flex items-center gap-2 rounded-md py-1 pr-2 transition-colors",
                active === s.id ? "bg-accent-soft font-medium text-accent-text" : "text-text-2 hover:bg-surface-3 hover:text-text",
              )}
              style={{ paddingLeft: 8 + (s.level - 1) * 12 }}
            >
              <span className="min-w-0 flex-1 truncate">
                {s.number && <span className="mr-1.5 text-text-3">{s.number}</span>}
                {title}
              </span>
              {full ? <Check className="size-3 shrink-0 text-success" /> : part ? <span className="size-1.5 shrink-0 rounded-full bg-warning" /> : null}
            </a>
          );
        })}
    </nav>
  );
}

// ---------------- main tab ----------------
export function FulltextTab({ detail }: { detail: PaperDetail }) {
  const id = detail.paper.id;
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const aiLabel = useAiLabel();
  const reqs = useTranslateRequests(detail.fulltext?.stats?.words);
  const { data: settings } = useSettings();
  const update = useUpdateSettings();
  const runAi = useAiRunner(detail.paper.id);
  const tState = detail.ai.translate;
  const translating = tState.status === "running";
  const ft = useFulltext(id, translating);
  const [fetchJobId, setFetchJobId] = useState<string | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [active, setActive] = useState<string | null>(null);
  const fetchTried = useRef(false);
  const wasTranslating = useRef(translating);

  const fetchJob = useJob(fetchJobId, (j) => {
    setFetchJobId(null);
    qc.invalidateQueries({ queryKey: ["fulltext", id] });
    qc.invalidateQueries({ queryKey: ["paper", id] });
    if (j.status === "failed") toast({ tone: "error", title: "无法获取全文", description: j.error ?? undefined });
  });

  const startFetch = async (force: boolean) => {
    try {
      const r = await api.post<Job | { status: string }>(`/papers/${id}/fulltext`, { force });
      if ("id" in r) setFetchJobId(r.id);
      else qc.invalidateQueries({ queryKey: ["fulltext", id] });
    } catch (e) {
      toast({ tone: "error", title: "无法获取全文", description: errorMessage(e) });
    }
  };

  // Fetching the full text is free (no AI), so do it automatically when the tab opens.
  useEffect(() => {
    const d = ft.data;
    if (!d || d.available || fetchTried.current || fetchJobId) return;
    const j = d.job;
    if (j && isActive(j)) {
      setFetchJobId(j.id);
      return;
    }
    if (j && j.status === "failed") return;
    fetchTried.current = true;
    startFetch(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ft.data]);

  // one last refresh after a translation finishes
  useEffect(() => {
    if (wasTranslating.current && !translating) qc.invalidateQueries({ queryKey: ["fulltext", id] });
    wasTranslating.current = translating;
  }, [translating, id, qc]);

  const doc = ft.data?.doc;
  const tr: TMap = ft.data?.translations ?? {};
  const status = ft.data?.translation_status;
  const view: View = (settings?.reading.translation_view as View) ?? "bilingual";
  const fontSize = settings?.reading.font_size ?? "md";

  // highlight the section currently in view
  useEffect(() => {
    if (!doc) return;
    const els = Array.from(document.querySelectorAll<HTMLElement>("section[data-sid]"));
    const obs = new IntersectionObserver(
      (entries) => {
        const vis = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (vis[0]) setActive((vis[0].target as HTMLElement).dataset.sid ?? null);
      },
      { rootMargin: "-140px 0px -60% 0px" },
    );
    els.forEach((e) => obs.observe(e));
    return () => obs.disconnect();
  }, [doc]);

  const startTranslate = async (sections?: string[], force = false) => {
    try {
      await api.post(`/papers/${id}/translate`, { sections: sections ?? null, force });
      qc.invalidateQueries({ queryKey: ["paper", id] });
    } catch (e) {
      toast({ tone: "error", title: "无法开始翻译", description: errorMessage(e) });
    }
  };

  const setView = (v: View) => settings && update.mutate({ reading: { ...settings.reading, translation_view: v } });
  const setSize = (s: "sm" | "md" | "lg") => settings && update.mutate({ reading: { ...settings.reading, font_size: s } });

  const bodySections = useMemo(() => doc?.sections.filter((s) => s.kind !== "references") ?? [], [doc]);
  const refSections = useMemo(() => doc?.sections.filter((s) => s.kind === "references") ?? [], [doc]);

  const canTranslate = detail.ai_configured && tState.enabled && !translating;

  // ---------- loading / unavailable states ----------
  if (ft.isLoading || (!doc && (fetchJobId || isActive(ft.data?.job)))) {
    return (
      <Card className="p-6">
        <div className="flex items-center gap-3">
          <Loader2 className="size-5 animate-spin text-accent" />
          <div>
            <div className="font-medium text-text">正在获取全文…</div>
            <div className="text-[13px] text-text-2">{fetchJob.data?.message ?? "优先使用 arXiv 的结构化 HTML 版本，以保留章节、公式与图表"}</div>
          </div>
        </div>
        <div className="mt-6 space-y-3">
          <Skeleton className="h-6 w-1/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-11/12" />
          <Skeleton className="h-4 w-4/5" />
        </div>
      </Card>
    );
  }

  if (!doc) {
    const err = ft.data?.job?.error;
    const absState = detail.ai.abstract_translation;
    return (
      <div className="space-y-4">
        <Card className="p-6">
          <div className="flex items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-warning-soft text-warning">
              <FileWarning className="size-5" />
            </span>
            <div className="min-w-0 flex-1">
              <h3 className="font-semibold text-text">无法获取这篇论文的全文</h3>
              <p className="mt-1 text-sm leading-relaxed text-text-2">{err ?? "没有找到可合法访问的开放全文。"}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button size="sm" icon={<RefreshCw className="size-3.5" />} onClick={() => startFetch(true)}>
                  重新尝试
                </Button>
                {detail.paper.url && (
                  <a href={detail.paper.url} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />}>
                      打开原文页面
                    </Button>
                  </a>
                )}
              </div>
            </div>
          </div>
        </Card>
        {detail.paper.abstract && (
          <Notice
            tone="accent"
            icon={<Languages className="size-4" />}
            title="可以先翻译摘要"
            action={
              !absState.result && detail.ai_configured ? (
                <Button size="sm" variant="primary" loading={absState.status === "running"} onClick={() => runAi("abstract_translation")}>
                  翻译摘要
                </Button>
              ) : undefined
            }
          >
            注意：这只是<strong className="font-semibold text-text">摘要翻译</strong>，不是全文翻译。
            {absState.result && <p className="zh mt-3 text-[15px] leading-relaxed text-text">{absState.result.content.abstract_zh}</p>}
          </Notice>
        )}
      </div>
    );
  }

  // ---------- translation status ----------
  const done = status?.done ?? 0;
  const total = status?.total ?? 0;
  const complete = total > 0 && done >= total;
  const job = tState.job;

  return (
    <div>
      {/* toolbar */}
      <div className="sticky top-[104px] z-20 -mx-4 mb-4 border-b border-border bg-bg/90 px-4 py-2.5 backdrop-blur sm:-mx-6 sm:px-6 lg:top-[49px]">
        <div className="flex flex-wrap items-center gap-2">
          <Segmented<View>
            size="sm"
            value={view}
            onChange={setView}
            options={[
              { value: "en", label: "原文" },
              { value: "bilingual", label: "对照" },
              { value: "zh", label: "译文" },
            ]}
          />
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {translating ? (
              <div className="flex items-center gap-2.5">
                <div className="hidden w-44 sm:block">
                  <ProgressBar value={done} max={total || 1} />
                  <div className="mt-0.5 truncate text-[11px] text-text-3">{job?.message}</div>
                </div>
                <span className="text-xs tabular-nums text-text-2">
                  {done}/{total}
                </span>
                <Button size="sm" variant="ghost" icon={<Square className="size-3.5" />} onClick={() => api.post(`/papers/${id}/translate/cancel`)}>
                  停止
                </Button>
              </div>
            ) : complete ? (
              <Badge tone="success" icon={<Check className="size-3" />}>
                全文已翻译
              </Badge>
            ) : !tState.enabled ? (
              <span className="text-xs text-text-3">全文翻译已在设置中关闭</span>
            ) : !detail.ai_configured ? (
              <Link to="/settings?s=ai">
                <Button size="sm" variant="soft" icon={<Languages className="size-3.5" />}>
                  配置 AI 服务后可翻译
                </Button>
              </Link>
            ) : (
              <>
                {done > 0 && (
                  <span className="text-xs tabular-nums text-text-3">
                    已翻译 {done}/{total} 段
                  </span>
                )}
                <Tooltip side="bottom" align="end" content={`调用 ${aiLabel} 翻译全文（预计约 ${estimateTokens(detail, (detail.fulltext?.stats?.words ?? 6000) / 500)} tokens${reqs ? `，约 ${reqs} 次请求` : ""}）。已翻译的部分会保存，中断后可继续。`}>
                  <Button size="sm" variant="primary" icon={<Play className="size-3.5" />} onClick={() => startTranslate()}>
                    {done > 0 ? `继续翻译（剩余 ${total - done} 段）` : "全文翻译"}
                  </Button>
                </Tooltip>
              </>
            )}

            {(ft.data?.glossary?.length ?? 0) > 0 && (
              <Popover
                align="end"
                className="w-[320px] p-3"
                trigger={({ toggle }) => (
                  <Button size="sm" variant="ghost" icon={<BookA className="size-3.5" />} onClick={toggle}>
                    术语表
                  </Button>
                )}
              >
                <div className="mb-2 text-xs text-text-3">翻译时统一使用以下译法</div>
                <div className="max-h-[320px] space-y-1 overflow-y-auto text-[13px]">
                  {ft.data!.glossary!.map((g) => (
                    <div key={g.en} className="grid grid-cols-2 gap-2 rounded-md px-1.5 py-1 hover:bg-surface-3">
                      <span className="font-serif text-text-2">{g.en}</span>
                      <span className="text-text">{g.zh}</span>
                    </div>
                  ))}
                </div>
              </Popover>
            )}

            <Popover
              align="end"
              className="w-[230px]"
              trigger={({ toggle }) => (
                <Button size="sm" variant="ghost" icon={<MoreHorizontal className="size-4" />} onClick={toggle} aria-label="更多" />
              )}
            >
              {(close) => (
                <>
                  <div className="px-2.5 pb-1 pt-1.5 text-[11px] font-medium text-text-3">字号</div>
                  <div className="flex gap-1 px-1.5 pb-1.5">
                    {(["sm", "md", "lg"] as const).map((s) => (
                      <button
                        key={s}
                        onClick={() => setSize(s)}
                        className={cn("flex h-8 flex-1 items-center justify-center rounded-md", fontSize === s ? "bg-accent-soft text-accent-text" : "hover:bg-surface-3 text-text-2")}
                      >
                        <Type className={s === "sm" ? "size-3" : s === "md" ? "size-3.5" : "size-4"} />
                      </button>
                    ))}
                  </div>
                  <div className="my-1 border-t border-border" />
                  <a href={`/api/papers/${id}/export?type=translation&mode=bilingual`} onClick={close}>
                    <MenuItem icon={<Download className="size-4" />}>导出双语 Markdown</MenuItem>
                  </a>
                  <a href={`/api/papers/${id}/export?type=translation&mode=zh`} onClick={close}>
                    <MenuItem icon={<Download className="size-4" />}>导出译文 Markdown</MenuItem>
                  </a>
                  <div className="my-1 border-t border-border" />
                  {canTranslate && done > 0 && (
                    <MenuItem
                      icon={<RotateCcw className="size-4" />}
                      onClick={async () => {
                        close();
                        if (await confirm({ title: "重新翻译全文？", description: `将删除现有译文并重新调用 ${aiLabel} 翻译整篇论文。`, confirmText: "重新翻译", danger: true }))
                          startTranslate(undefined, true);
                      }}
                    >
                      重新翻译全文
                    </MenuItem>
                  )}
                  <MenuItem
                    icon={<RefreshCw className="size-4" />}
                    disabled={translating}
                    onClick={async () => {
                      close();
                      if (await confirm({ title: "重新获取全文？", description: "会重新下载并解析全文。已有译文将被清除（因为段落可能变化）。", confirmText: "重新获取", danger: done > 0 }))
                        startFetch(true);
                    }}
                  >
                    重新获取全文
                  </MenuItem>
                </>
              )}
            </Popover>
          </div>
        </div>
        {translating && (
          <div className="mt-2 sm:hidden">
            <ProgressBar value={done} max={total || 1} />
          </div>
        )}
      </div>

      {!translating && tState.status === "partial" && job?.message && !complete && (
        <Notice tone="warning" icon={<AlertTriangle className="size-4" />} className="mb-4" title="翻译未全部完成">
          {job.error ?? job.message}
        </Notice>
      )}
      {!translating && tState.status === "failed" && job?.error && (
        <Notice tone="danger" icon={<AlertTriangle className="size-4" />} className="mb-4" title="翻译失败">
          {job.error}
          {done > 0 && " 已完成的部分已保存，点击「继续翻译」可接着翻译。"}
        </Notice>
      )}

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden xl:block">
          <div className="sticky top-[118px] max-h-[calc(100vh-140px)] overflow-y-auto pb-6">
            <div className="mb-2 flex items-center gap-1.5 px-2 text-xs font-medium text-text-3">
              <ListTree className="size-3.5" /> 目录
            </div>
            <Toc doc={doc} tr={tr} view={view} status={status} active={active} />
          </div>
        </aside>

        <article className="reader min-w-0" data-size={fontSize}>
          <div className="mb-6 flex flex-wrap items-center gap-2 font-sans text-xs text-text-3">
            <Badge tone={doc.source === "arxiv_html" ? "success" : "warning"}>{doc.source_label}</Badge>
            <span>
              {doc.stats.sections} 节 · 约 {Math.round(doc.stats.words / 100) / 10}k 词 · {doc.stats.figures} 图 · {doc.stats.tables} 表 · {doc.stats.equations} 个公式
            </span>
            <a href={doc.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 hover:text-accent-text">
              来源 <ExternalLink className="size-3" />
            </a>
          </div>
          {doc.warnings.map((w) => (
            <Notice key={w} tone="warning" icon={<AlertTriangle className="size-4" />} className="mb-3 font-sans">
              {w}
            </Notice>
          ))}

          <div className="mx-auto max-w-[760px]">
            {bodySections.map((s) => (
              <SectionView
                key={s.id}
                s={s}
                tr={tr}
                view={view}
                done={status?.sections[s.id]?.done ?? 0}
                total={status?.sections[s.id]?.total ?? 0}
                onImage={setImage}
                canTranslate={canTranslate}
                onRetranslate={async (sid) => {
                  const has = (status?.sections[sid]?.done ?? 0) > 0;
                  if (!has || (await confirm({ title: "重新翻译本节？", description: "将覆盖本节现有译文。", confirmText: "重新翻译" })))
                    startTranslate([sid], has);
                }}
              />
            ))}
            <References sections={refSections} />
          </div>
        </article>
      </div>

      <Dialog open={!!image} onClose={() => setImage(null)} title="图片" width="max-w-5xl">
        {image && <img src={image} alt="" className="mx-auto max-h-[78vh] w-auto rounded-lg bg-white" />}
      </Dialog>
    </div>
  );
}
