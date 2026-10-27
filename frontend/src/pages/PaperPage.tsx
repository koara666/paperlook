import {
  ArrowLeft,
  Check,
  Copy,
  Download,
  ExternalLink,
  EyeOff,
  FileText,
  Languages,
  Layers,
  Lightbulb,
  LayoutGrid,
  MoreHorizontal,
  NotebookText,
  Star,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { usePaper, usePaperState } from "../api/hooks";
import type { FeatureState } from "../api/types";
import { MenuItem, Popover, useToast } from "../components/ui/overlay";
import { Badge, Button, Card, EmptyState, Skeleton } from "../components/ui/primitives";
import { cn } from "../lib/cn";
import { authorsShort, longDate } from "../lib/format";
import { MathText, plainText } from "../lib/math";
import { AiPanel, useAiRunner } from "./paper/AiPanel";
import { ContributionsView, ModulesView, SummaryView } from "./paper/AiViews";
import { FulltextTab } from "./paper/FulltextTab";
import { OverviewTab } from "./paper/OverviewTab";

type Tab = "overview" | "fulltext" | "summary" | "modules" | "contributions";

function Dot({ st }: { st?: FeatureState }) {
  if (!st) return null;
  if (st.status === "running") return <span className="size-1.5 animate-pulse rounded-full bg-accent" />;
  if (st.status === "done") return <span className="size-1.5 rounded-full bg-success" />;
  if (st.status === "partial") return <span className="size-1.5 rounded-full bg-warning" />;
  if (st.status === "failed") return <span className="size-1.5 rounded-full bg-danger" />;
  return null;
}

export default function PaperPage() {
  const { id } = useParams();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "overview";
  const navigate = useNavigate();
  const { data, isLoading, error } = usePaper(id);
  const setState = usePaperState(id ?? "");
  const toast = useToast();
  const [authorsOpen, setAuthorsOpen] = useState(false);
  const marked = useRef(false);
  const pendingRun = useRef<Tab | null>(null);
  const runAi = useAiRunner(id ?? "");

  // Opening a paper marks it as read (can be undone with the button).
  useEffect(() => {
    if (data && !marked.current) {
      marked.current = true;
      setState.mutate(data.state.read ? { opened: true } : { opened: true, read: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.paper.id]);

  useEffect(() => {
    if (data) document.title = `${plainText(data.paper.title).slice(0, 60)} · PaperLook`;
    return () => {
      document.title = "PaperLook · 每日论文";
    };
  }, [data?.paper.title]);

  // "生成" from the overview tiles: switch tab, then trigger once the tab is shown.
  useEffect(() => {
    if (pendingRun.current && data && pendingRun.current === tab) {
      const k = pendingRun.current as "summary" | "modules" | "contributions";
      pendingRun.current = null;
      if (data.ai[k].status !== "running" && !data.ai[k].result) runAi(k);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, data]);

  const go = (t: Tab, autoRun = false) => {
    if (autoRun) pendingRun.current = t;
    setParams(t === "overview" ? {} : { tab: t }, { replace: false });
    window.scrollTo({ top: 0 });
  };

  if (isLoading) {
    return (
      <div className="mx-auto max-w-[1180px] px-4 pt-8 sm:px-6">
        <Skeleton className="h-5 w-24" />
        <Skeleton className="mt-6 h-9 w-3/4" />
        <Skeleton className="mt-3 h-5 w-1/2" />
        <Skeleton className="mt-10 h-64 w-full rounded-2xl" />
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="mx-auto max-w-[720px] px-4 pt-16">
        <Card>
          <EmptyState icon={<FileText className="size-6" />} title="找不到这篇论文" description={(error as Error)?.message}
            action={<Button onClick={() => navigate("/")}>返回今日推荐</Button>} />
        </Card>
      </div>
    );
  }

  const p = data.paper;
  const s = data.state;
  const titleZh = data.ai.abstract_translation.result?.content.title_zh || data.recommendation?.ai?.title_zh;
  const venueSignal = data.recommendation?.breakdown.quality_signals.find((q) => q.key === "venue");

  const tabs: { key: Tab; label: string; icon: React.ReactNode; st?: FeatureState }[] = [
    { key: "overview", label: "概览", icon: <LayoutGrid className="size-4" /> },
    { key: "fulltext", label: "全文 · 翻译", icon: <Languages className="size-4" />, st: data.ai.translate },
    { key: "summary", label: "AI 总结", icon: <NotebookText className="size-4" />, st: data.ai.summary },
    { key: "modules", label: "关键模块", icon: <Layers className="size-4" />, st: data.ai.modules },
    { key: "contributions", label: "创新点", icon: <Lightbulb className="size-4" />, st: data.ai.contributions },
  ];

  const copyCitation = async () => {
    const text = `${p.authors.slice(0, 6).join(", ")}${p.authors.length > 6 ? " et al." : ""}. ${plainText(p.title)}. ${p.venue ?? (p.arxiv_id ? `arXiv:${p.arxiv_id}` : "")}, ${p.published?.slice(0, 4) ?? ""}. ${p.url ?? ""}`;
    try {
      await navigator.clipboard.writeText(text);
      toast({ tone: "success", title: "已复制引用信息" });
    } catch {
      toast({ tone: "error", title: "复制失败" });
    }
  };

  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-24 sm:px-6">
      {/* header */}
      <div className="pt-5 lg:pt-8">
        <div className="mb-4 flex items-center justify-between gap-2">
          <button onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/"))} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 -ml-2 text-[13px] text-text-2 hover:bg-surface-3 hover:text-text">
            <ArrowLeft className="size-4" /> 返回
          </button>
          <div className="flex items-center gap-1">
            {p.url && (
              <a href={p.url} target="_blank" rel="noreferrer">
                <Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />}>
                  <span className="hidden sm:inline">原文页面</span>
                </Button>
              </a>
            )}
            {p.pdf_url && (
              <a href={p.pdf_url} target="_blank" rel="noreferrer">
                <Button size="sm" variant="ghost" icon={<FileText className="size-3.5" />}>
                  PDF
                </Button>
              </a>
            )}
            <Button size="sm" variant={s.starred ? "soft" : "ghost"} icon={<Star className={cn("size-3.5", s.starred && "fill-current text-[#e9a93a]")} />}
              onClick={() => setState.mutate({ starred: !s.starred })}>
              <span className="hidden sm:inline">{s.starred ? "已收藏" : "收藏"}</span>
            </Button>
            <Button size="sm" variant="ghost" icon={<Check className={cn("size-3.5", s.read && "text-success")} />} onClick={() => setState.mutate({ read: !s.read })}>
              <span className="hidden sm:inline">{s.read ? "已读" : "标为已读"}</span>
            </Button>
            <Popover
              align="end"
              className="w-[220px]"
              trigger={({ toggle }) => <Button size="sm" variant="ghost" icon={<MoreHorizontal className="size-4" />} onClick={toggle} aria-label="更多操作" />}
            >
              {(close) => (
                <>
                  <MenuItem icon={<Copy className="size-4" />} onClick={() => { close(); copyCitation(); }}>
                    复制引用信息
                  </MenuItem>
                  <a href={`/api/papers/${p.id}/export?type=analysis`} onClick={close}>
                    <MenuItem icon={<Download className="size-4" />}>导出 AI 分析（Markdown）</MenuItem>
                  </a>
                  <div className="my-1 border-t border-border" />
                  <MenuItem
                    icon={<EyeOff className="size-4" />}
                    onClick={() => {
                      close();
                      setState.mutate({ dismissed: !s.dismissed }, { onSuccess: () => toast({ tone: "success", title: s.dismissed ? "已恢复显示" : "已标记为不感兴趣" }) });
                    }}
                  >
                    {s.dismissed ? "恢复显示" : "不感兴趣"}
                  </MenuItem>
                </>
              )}
            </Popover>
          </div>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2">
          {data.recommendation && <Badge tone="accent">{data.recommendation.direction_name}</Badge>}
          {venueSignal && <Badge tone="warning">{venueSignal.label.replace("作者注明：", "")}</Badge>}
          {p.published && <span className="text-[13px] text-text-3">{longDate(p.published)} 发布</span>}
        </div>
        <h1 className="max-w-[920px] font-serif text-[26px] font-semibold leading-[1.25] tracking-[-0.01em] text-text sm:text-[30px]">
          <MathText text={p.title} />
        </h1>
        {titleZh && <p className="mt-2 max-w-[920px] text-[17px] text-text-2">{titleZh}</p>}
        <p className="mt-3 max-w-[920px] text-[14px] leading-relaxed text-text-2">
          {authorsOpen ? p.authors.join(", ") : authorsShort(p.authors, p.authors.length, 6)}
          {p.authors.length > 6 && (
            <button onClick={() => setAuthorsOpen(!authorsOpen)} className="ml-2 text-[13px] text-accent-text hover:underline">
              {authorsOpen ? "收起" : "展开全部"}
            </button>
          )}
        </p>
      </div>

      {/* tabs */}
      <div className="sticky top-14 z-20 -mx-4 mt-6 border-b border-border bg-bg/90 px-4 backdrop-blur sm:-mx-6 sm:px-6 lg:top-0">
        <div className="-mb-px flex gap-1 overflow-x-auto">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => go(t.key)}
              className={cn(
                "flex h-12 shrink-0 items-center gap-2 border-b-2 px-3 text-sm font-medium transition-colors",
                tab === t.key ? "border-accent text-text" : "border-transparent text-text-3 hover:text-text-2",
              )}
            >
              <span className={tab === t.key ? "text-accent" : ""}>{t.icon}</span>
              {t.label}
              <Dot st={t.st} />
            </button>
          ))}
        </div>
      </div>

      <div className="pt-6">
        {tab === "overview" && <OverviewTab detail={data} go={go} />}
        {tab === "fulltext" && <FulltextTab detail={data} />}
        {tab === "summary" && (
          <div className="mx-auto max-w-[960px]">
            <AiPanel detail={data} kind="summary" state={data.ai.summary} icon={<NotebookText className="size-6" />} title="论文总结"
              description="快速了解这篇论文研究什么、为什么重要、怎么做的、效果如何，以及是否值得精读。"
              outputs={["研究问题与动机", "方法与核心思想", "数据集、指标与主要结果", "实验是否充分", "局限性（区分作者承认 / AI 评估）", "阅读建议与优先章节"]}>
              {(c) => <SummaryView c={c} />}
            </AiPanel>
          </div>
        )}
        {tab === "modules" && (
          <div className="mx-auto max-w-[960px]">
            <AiPanel detail={data} kind="modules" state={data.ai.modules} icon={<Layers className="size-6" />} title="关键模块分析"
              description="识别论文中的重要技术模块及其协作方式。对于综述、理论等不含模块结构的论文，会如实说明并梳理论证结构。"
              outputs={["整体架构概述", "各模块的职责、输入输出与原理", "模块之间的数据流", "关键公式", "本文提出 / 沿用的区分", "关键设计选择"]}>
              {(c) => <ModulesView c={c} />}
            </AiPanel>
          </div>
        )}
        {tab === "contributions" && (
          <div className="mx-auto max-w-[960px]">
            <AiPanel detail={data} kind="contributions" state={data.ai.contributions} icon={<Lightbulb className="size-6" />} title="创新点提取"
              description="提取论文的主要贡献，并严格区分：作者原文声明的贡献（附原文引用并自动核验）、基于内容归纳的贡献、以及 AI 推断的潜在价值。"
              outputs={["作者明确声明的贡献 + 原文引用", "引用真实性自动核验", "基于内容归纳的贡献", "相比已有方法的改进", "实验支撑强度", "AI 推断的潜在价值（单独标注）"]}>
              {(c) => <ContributionsView c={c} />}
            </AiPanel>
          </div>
        )}
      </div>
    </div>
  );
}
