import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, FileText, KeyRound, Languages, Loader2, RotateCcw, Settings2, Sparkles } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../../api/client";
import { useAiLabel, useRunAi } from "../../api/hooks";
import type { AiKind, FeatureState, PaperDetail } from "../../api/types";
import { useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, Notice, ProgressBar, Skeleton } from "../../components/ui/primitives";
import { cap, t } from "../../i18n";
import { languageName, timeAgo, tokens } from "../../lib/format";

export function useAiRunner(paperId: string) {
  const run = useRunAi(paperId);
  const toast = useToast();
  const qc = useQueryClient();
  return (kind: AiKind, force = false) =>
    run.mutate(
      { kind, force },
      {
        onSuccess: () => qc.invalidateQueries({ queryKey: ["paper", paperId] }),
        onError: (e) => toast({ tone: "error", title: t("ai.cannot_start"), description: errorMessage(e) }),
      },
    );
}

export function estimateTokens(detail: PaperDetail, outputK = 3): string {
  const words = detail.fulltext?.stats?.words;
  const input = words ? words * 1.45 : (detail.paper.abstract?.split(/\s+/).length ?? 200) * 1.5 + 800;
  return tokens(Math.round((input + outputK * 1000) / 1000) * 1000);
}

function Elapsed({ since }: { since?: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  if (!since) return null;
  const s = Math.max(0, Math.round((now - new Date(since).getTime()) / 1000));
  return <span className="tabular-nums">{s < 60 ? t("ai.elapsed_s", { s }) : t("ai.elapsed_ms", { m: Math.floor(s / 60), s: s % 60 })}</span>;
}

export function AiPanel({
  detail,
  kind,
  state,
  icon,
  title,
  description,
  outputs,
  children,
}: {
  detail: PaperDetail;
  kind: AiKind;
  state: FeatureState;
  icon: ReactNode;
  title: string;
  description: string;
  outputs: string[];
  children: (content: any) => ReactNode;
}) {
  const runAi = useAiRunner(detail.paper.id);
  const confirm = useConfirm();
  const aiLabel = useAiLabel();
  const res = state.result;
  const job = state.job;
  const target = detail.language?.target;

  if (!detail.ai_configured && !res) {
    return (
      <Card className="px-6 py-10 text-center">
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-warning-soft text-warning">
          <KeyRound className="size-6" />
        </div>
        <h3 className="text-base font-semibold text-text">{t("ai.need_key", { provider: aiLabel })}</h3>
        <p className="mx-auto mt-1.5 max-w-md text-sm text-text-2">{t("ai.need_key_desc", { feature: title, provider: aiLabel })}</p>
        <Link to="/settings?s=ai">
          <Button variant="primary" className="mt-5" icon={<Settings2 className="size-4" />}>
            {t("ai.go_configure")}
          </Button>
        </Link>
      </Card>
    );
  }

  if (state.status === "disabled") {
    return (
      <Notice tone="neutral" icon={<AlertCircle className="size-4" />} title={t("ai.disabled", { feature: title })}
        action={<Link to="/settings?s=features"><Button size="sm">{t("ai.enable")}</Button></Link>}>
        {t("ai.disabled_desc")}
      </Notice>
    );
  }

  if (state.status === "running") {
    return (
      <Card className="px-6 py-6">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-xl bg-accent-soft text-accent">
            <Loader2 className="size-5 animate-spin" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-text">{t("ai.generating", { feature: title })}</div>
            <div className="mt-0.5 text-[13px] text-text-2">
              {job?.message} · {t("ai.elapsed")} <Elapsed since={job?.created_at} />
            </div>
          </div>
        </div>
        <ProgressBar indeterminate className="mt-4" />
        <div className="mt-6 space-y-3">
          <Skeleton className="h-5 w-2/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-24 w-full rounded-xl" />
        </div>
        <p className="mt-4 text-xs text-text-3">{t("ai.background")}</p>
      </Card>
    );
  }

  if (!res) {
    const failed = state.status === "failed" && job?.error;
    const ftReady = !!detail.fulltext;
    return (
      <Card className="overflow-hidden">
        <div className="px-6 py-8 sm:px-8">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-accent-soft text-accent">{icon}</div>
          <h3 className="mt-4 text-lg font-semibold text-text">{cap(title)}</h3>
          <p className="mt-1 max-w-xl text-sm leading-relaxed text-text-2">{description}</p>
          <ul className="mt-4 grid max-w-xl grid-cols-1 gap-1.5 sm:grid-cols-2">
            {outputs.map((o) => (
              <li key={o} className="flex items-center gap-2 text-[13px] text-text-2">
                <span className="size-1 shrink-0 rounded-full bg-accent" />
                {o}
              </li>
            ))}
          </ul>
          {failed && (
            <Notice tone="danger" icon={<AlertCircle className="size-4" />} title={t("ai.last_failed")} className="mt-5">
              {job!.error}
            </Notice>
          )}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button variant="primary" size="lg" icon={failed ? <RotateCcw className="size-4" /> : <Sparkles className="size-4" />} onClick={() => runAi(kind)}>
              {failed ? t("common.retry") : t("ai.generate", { feature: title })}
            </Button>
            <span className="flex flex-wrap items-center gap-1.5 text-[13px] text-text-3">
              <FileText className="size-3.5" />
              {ftReady ? t("ai.basis_fulltext_src", { source: detail.fulltext!.source_label }) : t("ai.basis_auto")}
              <span className="text-border-strong">·</span>
              {t("ai.estimate", { tokens: estimateTokens(detail) })}
            </span>
          </div>
          {target && <p className="mt-3 text-[12px] text-text-3">{t("ai.output_lang", { language: languageName(target) })}</p>}
        </div>
      </Card>
    );
  }

  const basis = res.basis;
  const usage = res.usage || {};
  const otherLang = !!(res.lang && target && res.lang !== target);
  return (
    <div className="space-y-4 animate-fade-in">
      {otherLang && (
        <Notice
          tone="accent"
          icon={<Languages className="size-4" />}
          title={t("ai.other_lang", { language: languageName(res.lang) })}
          action={
            <Button size="sm" variant="primary" onClick={() => runAi(kind, true)}>
              {t("ai.regenerate_in", { language: languageName(target) })}
            </Button>
          }
        >
          {t("ai.other_lang_desc")}
        </Notice>
      )}
      {basis?.type === "abstract" && (
        <Notice
          tone="warning"
          icon={<AlertCircle className="size-4" />}
          title={t("ai.abstract_only")}
          action={
            state.upgradable ? (
              <Button size="sm" variant="primary" onClick={() => runAi(kind, true)}>
                {t("ai.regenerate_fulltext")}
              </Button>
            ) : undefined
          }
        >
          {basis.reason ? t("ai.abstract_reason", { reason: basis.reason }) : t("ai.no_fulltext")} {t("ai.abstract_caveat")}
        </Notice>
      )}
      {state.job?.status === "failed" && state.job.error && (
        <Notice tone="danger" icon={<AlertCircle className="size-4" />} title={t("ai.regen_failed")}>
          {state.job.error}
        </Notice>
      )}
      {children(res.content)}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface-2 px-4 py-2.5 text-xs text-text-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Badge tone={basis?.type === "fulltext" ? "success" : "warning"}>{basis?.type === "fulltext" ? t("ai.based_fulltext") : t("ai.based_abstract")}</Badge>
          {basis?.thinking && <Badge tone="accent">{t("ai.thinking")}</Badge>}
          <span>{res.model}</span>
          <span>{t("ai.generated_at", { when: timeAgo(res.created_at) })}</span>
          {(usage.prompt_tokens || usage.completion_tokens) && (
            <span>{t("ai.used_tokens", { tokens: tokens((usage.prompt_tokens ?? 0) + (usage.completion_tokens ?? 0)) })}</span>
          )}
          <span>{t("ai.disclaimer")}</span>
        </div>
        <Button
          size="xs"
          variant="ghost"
          icon={<RotateCcw className="size-3.5" />}
          onClick={async () => {
            if (await confirm({ title: t("ai.regen_q", { feature: title }), description: t("ai.regen_desc", { provider: aiLabel, tokens: estimateTokens(detail) }), confirmText: t("ai.regenerate") }))
              runAi(kind, true);
          }}
        >
          {t("ai.regenerate")}
        </Button>
      </div>
    </div>
  );
}
