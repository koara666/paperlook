import { ArrowRight, Check, ExternalLink, Info, KeyRound, Languages, Layers, Lightbulb, Loader2, NotebookText, Sparkles, TriangleAlert } from "lucide-react";
import { Link } from "react-router-dom";
import { useState, type ReactNode } from "react";
import { useAiLabel } from "../../api/hooks";
import type { FeatureState, PaperDetail } from "../../api/types";
import { BreakdownPanel, ScoreRing } from "../../components/papers/Score";
import { Badge, Button, Card, SectionTitle } from "../../components/ui/primitives";
import { cn } from "../../lib/cn";
import { SOURCE_LABEL, localDay, longDate, relativeDay } from "../../lib/format";
import { MathText } from "../../lib/math";
import { useAiRunner } from "./AiPanel";
import { NoteCard } from "./NoteCard";

type Tab = "overview" | "fulltext" | "summary" | "modules" | "contributions";

function statusLabel(st: FeatureState, isTranslate = false): { text: string; tone: "neutral" | "success" | "accent" | "danger" | "warning" } {
  if (st.status === "running") return { text: "进行中", tone: "accent" };
  if (st.status === "done") return { text: "已完成", tone: "success" };
  if (st.status === "partial") return { text: isTranslate ? `已翻译 ${st.progress?.done ?? 0}/${st.progress?.total ?? 0}` : "部分完成", tone: "warning" };
  if (st.status === "failed") return { text: "失败", tone: "danger" };
  if (st.status === "disabled") return { text: "已关闭", tone: "neutral" };
  return { text: "未生成", tone: "neutral" };
}

function ActionTile({ icon, title, desc, st, onOpen, onRun, isTranslate, disabled }: { icon: ReactNode; title: string; desc: string; st: FeatureState; onOpen: () => void; onRun: () => void; isTranslate?: boolean; disabled?: boolean }) {
  const lab = statusLabel(st, isTranslate);
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
            查看
          </Button>
        ) : disabled ? (
          <Link to="/settings?s=ai" className="block">
            <Button size="sm" variant="outline" className="w-full" icon={<KeyRound className="size-3.5" />}>
              配置后可用
            </Button>
          </Link>
        ) : (
          <Button size="sm" variant="soft" className="w-full" disabled={st.status === "disabled"} onClick={onRun} icon={<Sparkles className="size-3.5" />}>
            {st.status === "disabled" ? "已在设置中关闭" : st.status === "failed" ? "重试" : isTranslate ? "开始翻译" : "生成"}
          </Button>
        )}
      </div>
    </div>
  );
}

function InfoRow({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="grid grid-cols-[72px_1fr] gap-3 py-2 text-[13px]">
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
  const [showZh, setShowZh] = useState(true);
  const summary = detail.ai.summary.result?.content;
  const noAi = !detail.ai_configured;
  const aiLabel = useAiLabel();

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div className="min-w-0 space-y-6">
        {/* abstract */}
        <Card className="p-5 sm:p-6">
          <SectionTitle
            title="摘要"
            extra={
              abs.result ? (
                <button onClick={() => setShowZh(!showZh)} className="text-xs text-accent-text hover:underline">
                  {showZh ? "隐藏中文" : "显示中文"}
                </button>
              ) : detail.ai_configured && p.abstract ? (
                <Button size="xs" variant="ghost" icon={abs.status === "running" ? <Loader2 className="size-3 animate-spin" /> : <Languages className="size-3.5" />}
                  disabled={abs.status === "running"} onClick={() => runAi("abstract_translation")}>
                  {abs.status === "running" ? "翻译中…" : "翻译摘要"}
                </Button>
              ) : null
            }
          />
          {p.abstract ? (
            <p className="font-serif text-[16.5px] leading-[1.75] text-text">
              <MathText text={p.abstract} />
            </p>
          ) : (
            <p className="text-sm text-text-3">来源未提供摘要。</p>
          )}
          {abs.result && showZh && (
            <div className="mt-4 rounded-xl bg-surface-2 px-4 py-3">
              <div className="mb-1 text-xs font-medium text-text-3">摘要翻译（AI）</div>
              <p className="text-[15px] leading-[1.9] text-text">
                <MathText text={abs.result.content.abstract_zh} />
              </p>
            </div>
          )}
          {abs.status === "failed" && abs.job?.error && <p className="mt-3 text-[13px] text-danger">摘要翻译失败：{abs.job.error}</p>}
        </Card>

        {/* AI quick view */}
        {summary?.tldr && (
          <Card className="overflow-hidden">
            <div className="bg-gradient-to-br from-accent-soft to-surface p-5 sm:p-6">
              <div className="mb-2 flex items-center gap-2 text-xs font-medium text-accent-text">
                <Sparkles className="size-3.5" /> AI 速览
              </div>
              <p className="text-[16px] font-medium leading-relaxed text-text">
                <MathText text={String(summary.tldr)} />
              </p>
              {summary.problem?.question && (
                <p className="mt-3 text-[14px] leading-relaxed text-text-2">
                  <span className="font-medium text-text">研究问题：</span>
                  <MathText text={String(summary.problem.question)} />
                </p>
              )}
              {summary.method?.core_idea && (
                <p className="mt-1.5 text-[14px] leading-relaxed text-text-2">
                  <span className="font-medium text-text">核心思想：</span>
                  <MathText text={String(summary.method.core_idea)} />
                </p>
              )}
              <Button size="sm" variant="ghost" className="mt-3 -ml-2" icon={<ArrowRight className="size-3.5" />} onClick={() => go("summary")}>
                查看完整总结
              </Button>
            </div>
          </Card>
        )}

        <NoteCard key={p.id} paperId={p.id} note={detail.state.note} />

        {/* AI toolbox */}
        <div>
          <SectionTitle
            title="AI 精读工具"
            extra={<span className="text-xs text-text-3">{noAi ? "需要先配置 AI 服务的 API Key" : `点击后才会调用 ${aiLabel}，结果自动保存`}</span>}
          />
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <ActionTile icon={<Languages className="size-4" />} title="全文翻译" desc="保留章节、公式与图表的逐段翻译" st={detail.ai.translate} isTranslate
              disabled={noAi} onOpen={() => go("fulltext")} onRun={() => go("fulltext")} />
            <ActionTile icon={<NotebookText className="size-4" />} title="论文总结" desc="问题、方法、实验、结论与阅读建议" st={detail.ai.summary}
              disabled={noAi} onOpen={() => go("summary")} onRun={() => go("summary", true)} />
            <ActionTile icon={<Layers className="size-4" />} title="关键模块" desc="架构、核心算法与模块之间的协作" st={detail.ai.modules}
              disabled={noAi} onOpen={() => go("modules")} onRun={() => go("modules", true)} />
            <ActionTile icon={<Lightbulb className="size-4" />} title="创新点" desc="区分作者声明、内容归纳与 AI 推断" st={detail.ai.contributions}
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
                <div className="text-sm font-semibold text-text">推荐评分</div>
                <div className="text-xs text-text-3">
                  {rec.direction_name} · {relativeDay(localDay(rec.recommended_at))}推荐
                </div>
              </div>
            </div>
            <BreakdownPanel b={rec.breakdown} />
            {rec.ai?.reason && (
              <div className="mt-3 rounded-lg bg-accent-soft px-3 py-2 text-[13px] text-accent-text">AI 评估：{rec.ai.reason}</div>
            )}
          </Card>
        )}

        <Card className="p-5">
          <SectionTitle title="论文信息" className="mb-1" />
          <div className="divide-y divide-border">
            <InfoRow label="发布日期">
              {p.published ? longDate(p.published) : "未知"}
              {p.date_quality === "approx" && (
                <span className="ml-1 inline-flex items-center gap-0.5 text-warning">
                  <TriangleAlert className="size-3" />
                  近似
                </span>
              )}
              {p.date_note && <span className="mt-0.5 block text-xs text-text-3">{p.date_note}</span>}
            </InfoRow>
            {p.venue && <InfoRow label="发表于">{p.venue}</InfoRow>}
            {p.comment && <InfoRow label="作者备注">{p.comment}</InfoRow>}
            {p.journal_ref && <InfoRow label="期刊引用">{p.journal_ref}</InfoRow>}
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
              <InfoRow label="分类">
                <div className="flex flex-wrap gap-1">
                  {p.categories.map((c) => (
                    <Badge key={c} tone="outline">
                      {c}
                    </Badge>
                  ))}
                </div>
              </InfoRow>
            )}
            <InfoRow label="来源">
              <div className="flex flex-col gap-0.5">
                {p.sources.map((s) => (
                  <a key={s.source + s.id} href={s.url ?? "#"} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent-text hover:underline">
                    {SOURCE_LABEL[s.source] ?? s.source} <ExternalLink className="size-3" />
                  </a>
                ))}
              </div>
            </InfoRow>
            {(p.signals?.hf_upvotes || p.signals?.code_url || p.signals?.hf_github_repo) && (
              <InfoRow label="其他">
                <div className="flex flex-col gap-0.5">
                  {p.signals.hf_upvotes ? <span>Hugging Face {p.signals.hf_upvotes} 赞</span> : null}
                  {(p.signals.code_url || p.signals.hf_github_repo) && (
                    <a href={p.signals.code_url || p.signals.hf_github_repo} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-accent-text hover:underline">
                      代码仓库 <ExternalLink className="size-3" />
                    </a>
                  )}
                </div>
              </InfoRow>
            )}
          </div>
          <p className="mt-3 flex gap-1.5 text-[11px] leading-relaxed text-text-3">
            <Info className="mt-px size-3 shrink-0" />
            日期为论文首次公开发布的日期（arXiv 为 v1 提交日期），不是更新或收录日期。
          </p>
        </Card>
      </div>
    </div>
  );
}
