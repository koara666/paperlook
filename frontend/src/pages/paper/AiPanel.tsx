import { useQueryClient } from "@tanstack/react-query";
import { AlertCircle, FileText, KeyRound, Loader2, RotateCcw, Settings2, Sparkles } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { errorMessage } from "../../api/client";
import { useAiLabel, useRunAi } from "../../api/hooks";
import type { AiKind, FeatureState, PaperDetail } from "../../api/types";
import { useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, Notice, ProgressBar, Skeleton } from "../../components/ui/primitives";
import { timeAgo, tokens } from "../../lib/format";

export function useAiRunner(paperId: string) {
  const run = useRunAi(paperId);
  const toast = useToast();
  const qc = useQueryClient();
  return (kind: AiKind, force = false) =>
    run.mutate(
      { kind, force },
      {
        onSuccess: () => qc.invalidateQueries({ queryKey: ["paper", paperId] }),
        onError: (e) => toast({ tone: "error", title: "无法开始", description: errorMessage(e) }),
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
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  if (!since) return null;
  const s = Math.max(0, Math.round((now - new Date(since).getTime()) / 1000));
  return <span className="tabular-nums">{s < 60 ? `${s} 秒` : `${Math.floor(s / 60)} 分 ${s % 60} 秒`}</span>;
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

  if (!detail.ai_configured && !res) {
    return (
      <Card className="px-6 py-10 text-center">
        <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-warning-soft text-warning">
          <KeyRound className="size-6" />
        </div>
        <h3 className="text-base font-semibold text-text">需要先配置 {aiLabel} API Key</h3>
        <p className="mx-auto mt-1.5 max-w-md text-sm text-text-2">{title}需要调用 {aiLabel} 模型。配置完成后回到这里点击按钮即可生成。</p>
        <Link to="/settings?s=ai">
          <Button variant="primary" className="mt-5" icon={<Settings2 className="size-4" />}>
            前往配置
          </Button>
        </Link>
      </Card>
    );
  }

  if (state.status === "disabled") {
    return (
      <Notice tone="neutral" icon={<AlertCircle className="size-4" />} title={`「${title}」功能已关闭`}
        action={<Link to="/settings?s=features"><Button size="sm">去开启</Button></Link>}>
        你在设置中关闭了此功能，因此不会显示生成按钮。
      </Notice>
    );
  }

  if (state.status === "running") {
    return (
      <Card className="px-6 py-6">
        <div className="flex items-center gap-3">
          <span className="flex size-10 items-center justify-center rounded-xl bg-accent-soft text-accent">
            <Loader2 className="size-5 animate-spin" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-text">正在生成{title}…</div>
            <div className="mt-0.5 text-[13px] text-text-2">
              {job?.message} · 已用时 <Elapsed since={job?.created_at} />
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
        <p className="mt-4 text-xs text-text-3">可以离开此页面，生成会在后台继续；完成后结果会自动保存。</p>
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
          <h3 className="mt-4 text-lg font-semibold text-text">{title}</h3>
          <p className="mt-1 max-w-xl text-sm leading-relaxed text-text-2">{description}</p>
          <ul className="mt-4 grid max-w-xl grid-cols-1 gap-1.5 sm:grid-cols-2">
            {outputs.map((o) => (
              <li key={o} className="flex items-center gap-2 text-[13px] text-text-2">
                <span className="size-1 rounded-full bg-accent" />
                {o}
              </li>
            ))}
          </ul>
          {failed && (
            <Notice tone="danger" icon={<AlertCircle className="size-4" />} title="上次生成失败" className="mt-5">
              {job!.error}
            </Notice>
          )}
          <div className="mt-6 flex flex-wrap items-center gap-3">
            <Button variant="primary" size="lg" icon={failed ? <RotateCcw className="size-4" /> : <Sparkles className="size-4" />} onClick={() => runAi(kind)}>
              {failed ? "重试" : `生成${title}`}
            </Button>
            <span className="flex items-center gap-1.5 text-[13px] text-text-3">
              <FileText className="size-3.5" />
              {ftReady ? `基于全文（${detail.fulltext!.source_label}）` : "将自动获取全文；无法获取时仅基于摘要"}
              <span className="text-border-strong">·</span>预计约 {estimateTokens(detail)} tokens
            </span>
          </div>
        </div>
      </Card>
    );
  }

  const basis = res.basis;
  const usage = res.usage || {};
  return (
    <div className="space-y-4 animate-fade-in">
      {basis?.type === "abstract" && (
        <Notice
          tone="warning"
          icon={<AlertCircle className="size-4" />}
          title="以下内容仅基于摘要生成"
          action={
            state.upgradable ? (
              <Button size="sm" variant="primary" onClick={() => runAi(kind, true)}>
                基于全文重新生成
              </Button>
            ) : undefined
          }
        >
          {basis.reason ? `原因：${basis.reason}` : "未能获取全文。"} 涉及实验细节和模块的内容可能不完整，请以原文为准。
        </Notice>
      )}
      {state.job?.status === "failed" && state.job.error && (
        <Notice tone="danger" icon={<AlertCircle className="size-4" />} title="重新生成失败，以下为之前的结果">
          {state.job.error}
        </Notice>
      )}
      {children(res.content)}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-border bg-surface-2 px-4 py-2.5 text-xs text-text-3">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Badge tone={basis?.type === "fulltext" ? "success" : "warning"}>{basis?.type === "fulltext" ? "基于全文" : "仅基于摘要"}</Badge>
          {basis?.thinking && <Badge tone="accent">深度思考</Badge>}
          <span>{res.model}</span>
          <span>{timeAgo(res.created_at)}生成</span>
          {(usage.prompt_tokens || usage.completion_tokens) && (
            <span>
              消耗 {tokens((usage.prompt_tokens ?? 0) + (usage.completion_tokens ?? 0))} tokens
            </span>
          )}
          <span>内容由 AI 生成，可能存在错误，关键信息请核对原文</span>
        </div>
        <Button
          size="xs"
          variant="ghost"
          icon={<RotateCcw className="size-3.5" />}
          onClick={async () => {
            if (await confirm({ title: `重新生成${title}？`, description: `将再次调用 ${aiLabel}（预计约 ${estimateTokens(detail)} tokens），新结果会覆盖当前内容。`, confirmText: "重新生成" }))
              runAi(kind, true);
          }}
        >
          重新生成
        </Button>
      </div>
    </div>
  );
}
