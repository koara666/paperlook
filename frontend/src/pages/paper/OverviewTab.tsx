import { ArrowRight, Check, ExternalLink, Info, KeyRound, Languages, Layers, Lightbulb, Loader2, NotebookText, Sparkles, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { useState, type ReactNode } from "react";
import { useAiLabel } from "../../api/hooks";
import type { FeatureState, PaperDetail } from "../../api/types";
import { BreakdownPanel, ScoreRing } from "../../components/papers/Score";
import { Badge, Button, Card, SectionTitle } from "../../components/ui/primitives";
import { t } from "../../i18n";
import { cn } from "../../lib/cn";
import { SOURCE_LABEL, languageName, localDay, longDate, relativeDay } from "../../lib/format";
import { MathText } from "../../lib/math";
import { useAiRunner } from "./AiPanel";
import { NoteCard } from "./NoteCard";

type Tab = "overview" | "fulltext" | "summary" | "modules" | "contributions";

function statusLabel(st: FeatureState, isTranslate = false): { text: string; tone: "neutral" | "success" | "accent" | "danger" | "warning" } {
  if (st.status === "running") return { text: t("tile.running"), tone: "accent" };
  if (st.status === "done") return { text: t("tile.done"), tone: "success" };
  if (st.status === "partial")
    return { text: isTranslate ? t("tile.translated_n", { done: st.progress?.done ?? 0, total: st.progress?.total ?? 0 }) : t("tile.partial"), tone: "warning" };
  if (st.status === "failed") return { text: t("tile.failed"), tone: "danger" };
  if (st.status === "disabled") return { text: t("tile.disabled"), tone: "neutral" };
  return { text: t("tile.idle"), tone: "neutral" };
}

function ActionTile({ icon, title, desc, st, onOpen, onRun, isTranslate, disabled, notNeeded }: { icon: ReactNode; title: string; desc: string; st: FeatureState; onOpen: () => void; onRun: () => void; isTranslate?: boolean; disabled?: boolean; notNeeded?: string }) {
  const lab = notNeeded && st.status !== "done" && st.status !== "partial" ? { text: t("tile.not_needed"), tone: "neutral" as const } : statusLabel(st, isTranslate);
  const done = st.status === "done";
  return (
    <div className="flex flex-col rounded-xl border border-border bg-surface p-4 transition-colors hover:border-border-strong">
      <div className="flex items-start justify-between gap-2">
        <span className={cn("flex size-9 items-center justify-center rounded-lg", done ? "bg-success-soft text-success" : "bg-accent-soft text-accent-text")}>{icon}</span>
        <Badge tone={lab.tone} icon={st.status === "running" ? <Loader2 className="size-3 animate-spin" /> : done ? <Check className="size-3" /> : undefined}>
          {lab.text}
        </Badge>
      </div>
      <div className="mt-3 font-medium text-text">{title}</div>
      <p className="mt-0.5 flex-1 text-[13px] leading-relaxed text-text-3">{desc}</p>
      <div className="mt-3">
        {done || st.status === "running" || st.status === "partial" ? (
          <Button size="sm" variant="secondary" className="w-full" onClick={onOpen} icon={<ArrowRight className="size-3.5" />}>
            {t("tile.view")}
          </Button>
        ) : disabled ? (
          <Link to="/settings?s=ai" className="block">
            <Button size="sm" variant="outline" className="w-full" icon={<KeyRound className="size-3.5" />}>
              {t("tile.configure")}
            </Button>
          </Link>
        ) : notNeeded ? (
          <p className="rounded-lg bg-surface-2 px-2.5 py-1.5 text-center text-[12px] leading-snug text-text-3">{notNeeded}</p>
        ) : (
          <Button size="sm" variant="soft" className="w-full" disabled={st.status === "disabled"} onClick={onRun} icon={<Sparkles className="size-3.5" />}>
            {st.status === "disabled" ? t("tile.off_in_settings") : st.status === "failed" ? t("common.retry") : isTranslate ? t("tile.start_translate") : t("tile.generate")}
          </Button>
        )}
      </div>
    </div>
  );
}

function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[88px_1fr] gap-3 py-2 text-[13px]">
      <span className="text-text-3">{label}</span>
      <span className="min-w-0 break-words text-text">{children}</span>
    </div>
  );
}

export function OverviewTab({ detail, go }: { detail: PaperDetail; go: (t: Tab, autoRun?: boolean) => void }) {
  const p = detail.paper;
  const rec = detail.recommendation;
  const runAi = useAiRunner(detail.paper.id);
  const abs = detail.ai.abstract_translation;
  const [showTr, setShowTr] = useState(true);
  const lang = detail.language;
  const absLang = abs.result?.lang;
  const absOther = !!(abs.result && lang && absLang && absLang !== lang.target);
  const absText = abs.result ? abs.result.content.abstract ?? abs.result.content.abstract_zh : null;
  const translateNotNeeded = lang && !lang.translate_needed && detail.ai.translate.status !== "done" && detail.ai.translate.status !== "partial"
    ? t("tile.same_language", { language: languageName(lang.fulltext ?? lang.paper ?? "en") })
    : undefined;
  const summary = detail.ai.summary.result?.content;
  const summaryLang = detail.ai.summary.result?.lang;
  const noAi = !detail.ai_configured;
  const aiLabel = useAiLabel();

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0 space-y-6">
        {/* abstract */}
        <Card className="p-5 sm:p-6">
          <SectionTitle
            title={t("ov.abstract")}
            extra={
              abs.result && !absOther ? (
                <button onClick={() => setShowTr(!showTr)} className="text-xs text-accent-text hover:underline">
                  {showTr ? t("ov.hide_translation") : t("ov.show_translation")}
                </button>
              ) : detail.ai_configured && p.abstract && (lang?.abstract_translate_needed ?? true) ? (
                <Button size="xs" variant="ghost" icon={abs.status === "running" ? <Loader2 className="size-3 animate-spin" /> : <Languages className="size-3.5" />}
                  disabled={abs.status === "running"} onClick={() => runAi("abstract_translation", absOther)}>
                  {abs.status === "running" ? t("ov.translating") : absOther ? t("ov.translate_into", { language: languageName(lang!.target) }) : t("ov.translate_abstract")}
                </Button>
              ) : null
            }
          />
          {p.abstract ? (
            <p className="font-serif text-[16.5px] leading-[1.75] text-text">
              <MathText text={p.abstract} />
            </p>
          ) : (
            <p className="text-sm text-text-3">{t("ov.no_abstract")}</p>
          )}
          {abs.result && absText && (absOther ? (lang?.abstract_translate_needed ?? true) : showTr) && (
            <div className="mt-4 rounded-xl bg-surface-2 px-4 py-3">
              <div className="mb-1 text-xs font-medium text-text-3">
                {t("ov.abstract_translation", { language: languageName(absLang ?? "zh") })}
              </div>
              <p className="text-[15px] leading-[1.9] text-text">
                <MathText text={absText} />
              </p>
            </div>
          )}
          {abs.status === "failed" && abs.job?.error && <p className="mt-3 text-[13px] text-danger">{t("ov.abstract_failed", { error: abs.job.error })}</p>}
        </Card>

        {/* AI quick view */}
        {summary?.tldr && (
          <Card className="overflow-hidden">
            <div className="bg-gradient-to-br from-accent-soft to-surface p-5 sm:p-6">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium text-accent-text">
                <Sparkles className="size-3.5" /> {t("ov.ai_glance")}
                {summaryLang && lang && summaryLang !== lang.target && (
                  <span className="font-normal text-text-3">· {t("ov.generated_in", { language: languageName(summaryLang) })}</span>
                )}
              </div>
              <p className="text-[16px] font-medium leading-relaxed text-text">
                <MathText text={String(summary.tldr)} />
              </p>
              {summary.problem?.question && (
                <p className="mt-3 text-[14px] leading-relaxed text-text-2">
                  <span className="font-medium text-text">{t("ov.question")}</span>
                  <MathText text={String(summary.problem.question)} />
                </p>
              )}
              {summary.method?.core_idea && (
                <p className="mt-1.5 text-[14px] leading-relaxed text-text-2">
                  <span className="font-medium text-text">{t("ov.core_idea")}</span>
                  <MathText text={String(summary.method.core_idea)} />
                </p>
              )}
              <Button size="sm" variant="ghost" className="mt-3 -ml-2" icon={<ArrowRight className="size-3.5" />} onClick={() => go("summary")}>
                {t("ov.full_summary")}
              </Button>
            </div>
          </Card>
        )}

        <NoteCard key={p.id} paperId={p.id} note={detail.state.note} />

        {/* AI toolbox */}
        <div>
          <SectionTitle
            title={t("ov.tools")}
            extra={<span className="text-xs text-text-3">{noAi ? t("ov.tools_need_key") : t("ov.tools_hint", { provider: aiLabel })}</span>}
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <ActionTile icon={<Languages className="size-4" />} title={t("ov.tile.translate")} desc={t("ov.tile.translate_desc")} st={detail.ai.translate} isTranslate
              disabled={noAi} notNeeded={translateNotNeeded} onOpen={() => go("fulltext")} onRun={() => go("fulltext")} />
            <ActionTile icon={<NotebookText className="size-4" />} title={t("ov.tile.summary")} desc={t("ov.tile.summary_desc")} st={detail.ai.summary}
              disabled={noAi} onOpen={() => go("summary")} onRun={() => go("summary", true)} />
            <ActionTile icon={<Layers className="size-4" />} title={t("ov.tile.modules")} desc={t("ov.tile.modules_desc")} st={detail.ai.modules}
              disabled={noAi} onOpen={() => go("modules")} onRun={() => go("modules", true)} />
            <ActionTile icon={<Lightbulb className="size-4" />} title={t("ov.tile.contributions")} desc={t("ov.tile.contributions_desc")} st={detail.ai.contributions}
              disabled={noAi} onOpen={() => go("contributions")} onRun={() => go("contributions", true)} />
          </div>
        </div>
      </div>

      {/* side column */}
      <div className="space-y-6">
        {rec && (
          <Card className="p-5">
            <div className="mb-4 flex items-center gap-3">
              <ScoreRing score={rec.score} size={52} />
              <div>
                <div className="text-sm font-semibold text-text">{t("score.title")}</div>
                <div className="text-xs text-text-3">
                  {rec.direction_name} · {t("ov.recommended_when", { when: relativeDay(localDay(rec.recommended_at)) })}
                </div>
              </div>
            </div>
            <BreakdownPanel b={rec.breakdown} />
            {rec.ai?.reason && (!rec.ai.lang || rec.ai.lang === detail.language?.target) && (
              <div className="mt-3 rounded-lg bg-accent-soft px-3 py-2 text-[13px] text-accent-text">{t("ov.ai_assessment", { reason: rec.ai.reason })}</div>
            )}
          </Card>
        )}

        <Card className="p-5">
          <SectionTitle title={t("ov.info")} className="mb-1" />
          <div className="divide-y divide-border">
            <InfoRow label={t("ov.published")}>
              {p.published ? longDate(p.published) : t("ov.unknown")}
              {p.date_quality === "approx" && (
                <span className="ml-1 inline-flex items-center gap-0.5 text-warning">
                  <TriangleAlert className="size-3" />
                  {t("ov.approx")}
                </span>
              )}
              {p.date_note && <span className="mt-0.5 block text-xs text-text-3">{p.date_note}</span>}
            </InfoRow>
            {p.venue && <InfoRow label={t("ov.venue")}>{p.venue}</InfoRow>}
            {p.language && <InfoRow label={t("ov.language")}>{languageName(lang?.fulltext ?? p.language)}</InfoRow>}
            {p.comment && <InfoRow label={t("ov.comment")}>{p.comment}</InfoRow>}
            {p.journal_ref && <InfoRow label={t("ov.journal_ref")}>{p.journal_ref}</InfoRow>}
            {p.arxiv_id && (
              <InfoRow label="arXiv">
                <a className="inline-flex items-center gap-1 text-accent-text hover:underline" href={`https://arxiv.org/abs/${p.arxiv_id}`} target="_blank" rel="noreferrer">
                  {p.arxiv_id} <ExternalLink className="size-3" />
                </a>
              </InfoRow>
            )}
            {p.doi && !p.doi.startsWith("10.48550") && (
              <InfoRow label="DOI">
                <a className="inline-flex items-center gap-1 break-all text-accent-text hover:underline" href={`https://doi.org/${p.doi}`} target="_blank" rel="noreferrer">
                  {p.doi} <ExternalLink className="size-3 shrink-0" />
                </a>
              </InfoRow>
            )}
            {p.categories.length > 0 && (
              <InfoRow label={t("ov.categories")}>
                <div className="flex flex-wrap gap-1">
                  {p.categories.map((c) => (
                    <Badge key={c} tone="outline">
                      {c}
                    </Badge>
                  ))}
                </div>
              </InfoRow>
            )}
            <InfoRow label={t("ov.sources")}>
              <div className="flex flex-col gap-0.5">
                {p.sources.map((s) => (
                  <a key={s.source + s.id} href={s.url ?? "#"} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent-text hover:underline">
                    {SOURCE_LABEL[s.source] ?? s.source} <ExternalLink className="size-3" />
                  </a>
                ))}
              </div>
            </InfoRow>
            {(p.signals?.hf_upvotes || p.signals?.code_url || p.signals?.hf_github_repo) && (
              <InfoRow label={t("ov.other")}>
                <div className="flex flex-col gap-0.5">
                  {p.signals.hf_upvotes ? <span>{t("ov.hf_upvotes", { n: p.signals.hf_upvotes })}</span> : null}
                  {(p.signals.code_url || p.signals.hf_github_repo) && (
                    <a href={p.signals.code_url || p.signals.hf_github_repo} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent-text hover:underline">
                      {t("ov.code")} <ExternalLink className="size-3" />
                    </a>
                  )}
                </div>
              </InfoRow>
            )}
          </div>
          <p className="mt-3 flex gap-1.5 text-[11px] leading-relaxed text-text-3">
            <Info className="mt-px size-3 shrink-0" />
            {t("ov.date_note")}
          </p>
        </Card>
      </div>
    </div>
  );
}
