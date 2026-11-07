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
import { rich, t } from "../../i18n";
import { copyText } from "../../lib/clipboard";
import { cn } from "../../lib/cn";
import { languageName } from "../../lib/format";
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
          <span className="ml-2 inline-flex rounded bg-surface-3 px-1.5 align-middle font-sans text-[11px] text-text-3">{t("ft.untranslated")}</span>
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
                <button key={src} onClick={() => onImage(src)} className="overflow-hidden rounded-lg bg-white" title={t("ft.zoom")}>
                  <img src={src} alt={b.label ?? "figure"} loading="lazy" className="mx-auto max-h-[460px] w-auto object-contain" />
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-border px-3 py-6 text-center font-sans text-xs text-text-3">{t("ft.no_image")}</div>
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
    if (await copyText(plainText(`${titleZh ?? s.title}\n\n${parts.join("\n\n")}`))) toast({ tone: "success", title: t("ft.copied_section") });
    else toast({ tone: "error", title: t("common.copy_failed"), description: t("common.clipboard_denied") });
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
          <Tooltip content={t("ft.copy_section_tip")} align="end">
            <button onClick={copy} className="rounded-md p-1.5 text-text-3 hover:bg-surface-3 hover:text-text" aria-label={t("ft.copy_section")}>
              <ClipboardCopy className="size-3.5" />
            </button>
          </Tooltip>
          {canTranslate && total > 0 && (
            <Tooltip content={done ? t("ft.retranslate_section") : t("ft.translate_section")} align="end">
              <button onClick={() => onRetranslate(s.id)} className="rounded-md p-1.5 text-text-3 hover:bg-surface-3 hover:text-text" aria-label={t("ft.translate_section")}>
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
          {t("ft.references")} <span className="font-normal text-text-3">{t("ft.references_note", { n: refs.length })}</span>
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
  const target = detail.language?.target;
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
    if (j.status === "failed") toast({ tone: "error", title: t("ft.cannot_fetch"), description: j.error ?? undefined });
  });

  const startFetch = async (force: boolean) => {
    try {
      const r = await api.post<Job | { status: string }>(`/papers/${id}/fulltext`, { force });
      if ("id" in r) setFetchJobId(r.id);
      else qc.invalidateQueries({ queryKey: ["fulltext", id] });
    } catch (e) {
      toast({ tone: "error", title: t("ft.cannot_fetch"), description: errorMessage(e) });
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
      toast({ tone: "error", title: t("ft.cannot_translate"), description: errorMessage(e) });
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
            <div className="font-medium text-text">{t("ft.fetching")}</div>
            <div className="text-[13px] text-text-2">{fetchJob.data?.message ?? t("ft.fetching_hint")}</div>
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
              <h3 className="font-semibold text-text">{t("ft.unavailable")}</h3>
              <p className="mt-1 text-sm leading-relaxed text-text-2">{err ?? t("ft.no_open_copy")}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <Button size="sm" icon={<RefreshCw className="size-3.5" />} onClick={() => startFetch(true)}>
                  {t("ft.try_again")}
                </Button>
                {detail.paper.url && (
                  <a href={detail.paper.url} target="_blank" rel="noreferrer">
                    <Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />}>
                      {t("ft.open_original")}
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
            title={t("ft.translate_abstract_first")}
            action={
              !absState.result && detail.ai_configured ? (
                <Button size="sm" variant="primary" loading={absState.status === "running"} onClick={() => runAi("abstract_translation")}>
                  {t("ov.translate_abstract")}
                </Button>
              ) : undefined
            }
          >
            {rich("ft.abstract_only_note", {}, { b: (x) => <strong className="font-semibold text-text">{x}</strong> })}
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
  // A paper written in the output language needs no translation (unless one exists from before).
  const langInfo = ft.data?.language ?? detail.language;
  const noTranslation = !!langInfo && !langInfo.translate_needed && done === 0 && !translating;

  return (
    <div>
      {/* toolbar */}
      <div className="sticky top-[104px] z-20 -mx-4 mb-4 border-b border-border bg-bg/90 px-4 py-2.5 backdrop-blur sm:-mx-6 sm:px-6 lg:top-[49px]">
        <div className="flex flex-wrap items-center gap-2">
          {noTranslation ? (
            <span className="flex items-center gap-1.5 text-[13px] text-text-2">
              <Languages className="size-3.5 text-text-3" />
              {t("ft.same_language", { language: languageName(langInfo!.fulltext ?? langInfo!.paper ?? "en") })}
            </span>
          ) : (
          <Segmented<View>
            size="sm"
            value={view}
            onChange={setView}
            options={[
              { value: "en", label: t("ft.view.original") },
              { value: "bilingual", label: t("ft.view.bilingual") },
              { value: "zh", label: t("ft.view.translation") },
            ]}
          />
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            {noTranslation ? null : translating ? (
              <div className="flex items-center gap-2.5">
                <div className="hidden w-44 sm:block">
                  <ProgressBar value={done} max={total || 1} />
                  <div className="mt-0.5 truncate text-[11px] text-text-3">{job?.message}</div>
                </div>
                <span className="text-xs tabular-nums text-text-2">
                  {done}/{total}
                </span>
                <Button size="sm" variant="ghost" icon={<Square className="size-3.5" />} onClick={() => api.post(`/papers/${id}/translate/cancel`)}>
                  {t("common.stop")}
                </Button>
              </div>
            ) : complete ? (
              <Badge tone="success" icon={<Check className="size-3" />}>
                {t("ft.all_translated")}
              </Badge>
            ) : !tState.enabled ? (
              <span className="text-xs text-text-3">{t("ft.translate_off")}</span>
            ) : !detail.ai_configured ? (
              <Link to="/settings?s=ai">
                <Button size="sm" variant="soft" icon={<Languages className="size-3.5" />}>
                  {t("ft.configure_to_translate")}
                </Button>
              </Link>
            ) : (
              <>
                {done > 0 && (
                  <span className="text-xs tabular-nums text-text-3">
                    {t("ft.translated_n", { done, total })}
                  </span>
                )}
                <Tooltip side="bottom" align="end" content={t(reqs ? "ft.translate_tip_reqs" : "ft.translate_tip", { provider: aiLabel, tokens: estimateTokens(detail, (detail.fulltext?.stats?.words ?? 6000) / 500), reqs, language: languageName(target) })}>
                  <Button size="sm" variant="primary" icon={<Play className="size-3.5" />} onClick={() => startTranslate()}>
                    {done > 0 ? t("ft.continue", { n: total - done }) : t("ft.translate_into", { language: languageName(target) })}
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
                    {t("ft.glossary")}
                  </Button>
                )}
              >
                <div className="mb-2 text-xs text-text-3">{t("ft.glossary_hint")}</div>
                <div className="max-h-[320px] space-y-1 overflow-y-auto text-[13px]">
                  {ft.data!.glossary!.map((g) => (
                    <div key={g.src} className="grid grid-cols-2 gap-2 rounded-md px-1.5 py-1 hover:bg-surface-3">
                      <span className="font-serif text-text-2">{g.src}</span>
                      <span className="text-text">{g.tgt}</span>
                    </div>
                  ))}
                </div>
              </Popover>
            )}

            <Popover
              align="end"
              className="w-[230px]"
              trigger={({ toggle }) => (
                <Button size="sm" variant="ghost" icon={<MoreHorizontal className="size-4" />} onClick={toggle} aria-label={t("common.more")} />
              )}
            >
              {(close) => (
                <>
                  <div className="px-2.5 pb-1 pt-1.5 text-[11px] font-medium text-text-3">{t("ft.font_size")}</div>
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
                    <MenuItem icon={<Download className="size-4" />}>{t("ft.export_bilingual")}</MenuItem>
                  </a>
                  <a href={`/api/papers/${id}/export?type=translation&mode=zh`} onClick={close}>
                    <MenuItem icon={<Download className="size-4" />}>{t("ft.export_translation")}</MenuItem>
                  </a>
                  <div className="my-1 border-t border-border" />
                  {canTranslate && done > 0 && (
                    <MenuItem
                      icon={<RotateCcw className="size-4" />}
                      onClick={async () => {
                        close();
                        if (await confirm({ title: t("ft.retranslate_q"), description: t("ft.retranslate_desc", { provider: aiLabel }), confirmText: t("ft.retranslate"), danger: true }))
                          startTranslate(undefined, true);
                      }}
                    >
                      {t("ft.retranslate_all")}
                    </MenuItem>
                  )}
                  <MenuItem
                    icon={<RefreshCw className="size-4" />}
                    disabled={translating}
                    onClick={async () => {
                      close();
                      if (await confirm({ title: t("ft.refetch_q"), description: t("ft.refetch_desc"), confirmText: t("ft.refetch"), danger: done > 0 }))
                        startFetch(true);
                    }}
                  >
                    {t("ft.refetch_all")}
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
        <Notice tone="warning" icon={<AlertTriangle className="size-4" />} className="mb-4" title={t("ft.partial")}>
          {job.error ?? job.message}
        </Notice>
      )}
      {!translating && tState.status === "failed" && job?.error && (
        <Notice tone="danger" icon={<AlertTriangle className="size-4" />} className="mb-4" title={t("ft.failed")}>
          {job.error}
          {done > 0 && " " + t("ft.partial_saved")}
        </Notice>
      )}

      <div className="grid grid-cols-1 gap-8 xl:grid-cols-[220px_minmax(0,1fr)]">
        <aside className="hidden xl:block">
          <div className="sticky top-[118px] max-h-[calc(100vh-140px)] overflow-y-auto pb-6">
            <div className="mb-2 flex items-center gap-1.5 px-2 text-xs font-medium text-text-3">
              <ListTree className="size-3.5" /> {t("ft.toc")}
            </div>
            <Toc doc={doc} tr={tr} view={noTranslation ? "en" : view} status={status} active={active} />
          </div>
        </aside>

        <article className="reader min-w-0" data-size={fontSize}>
          <div className="mb-6 flex flex-wrap items-center gap-2 font-sans text-xs text-text-3">
            <Badge tone={doc.source === "arxiv_html" ? "success" : "warning"}>{doc.source_label}</Badge>
            <span>
              {t("ft.stats", { sections: doc.stats.sections, words: Math.round(doc.stats.words / 100) / 10, figures: doc.stats.figures, tables: doc.stats.tables, equations: doc.stats.equations })}
            </span>
            <a href={doc.source_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 hover:text-accent-text">
              {t("ft.source")} <ExternalLink className="size-3" />
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
                view={noTranslation ? "en" : view}
                done={status?.sections[s.id]?.done ?? 0}
                total={status?.sections[s.id]?.total ?? 0}
                onImage={setImage}
                canTranslate={canTranslate}
                onRetranslate={async (sid) => {
                  const has = (status?.sections[sid]?.done ?? 0) > 0;
                  if (!has || (await confirm({ title: t("ft.retranslate_section_q"), description: t("ft.retranslate_section_desc"), confirmText: t("ft.retranslate") })))
                    startTranslate([sid], has);
                }}
              />
            ))}
            <References sections={refSections} />
          </div>
        </article>
      </div>

      <Dialog open={!!image} onClose={() => setImage(null)} title={t("ft.image")} width="max-w-5xl">
        {image && <img src={image} alt="" className="mx-auto max-h-[78vh] w-auto rounded-lg bg-white" />}
      </Dialog>
    </div>
  );
}
