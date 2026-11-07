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
  Quote,
  Star,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { usePaper, usePaperState } from "../api/hooks";
import type { FeatureState } from "../api/types";
import { MenuItem, Popover, useToast } from "../components/ui/overlay";
import { Badge, Button, Card, EmptyState, Skeleton } from "../components/ui/primitives";
import { LanguageTag } from "../components/papers/PaperCard";
import { t } from "../i18n";
import { copyText } from "../lib/clipboard";
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
      document.title = t("app.title");
    };
  }, [data?.paper.title]);

  // "Generate" from the overview tiles: switch tab, then trigger once the tab is shown.
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
          <EmptyState icon={<FileText className="size-6" />} title={t("pp.not_found")} description={(error as Error)?.message}
            action={<Button onClick={() => navigate("/")}>{t("pp.back_today")}</Button>} />
        </Card>
      </div>
    );
  }

  const p = data.paper;
  const s = data.state;
  // Translated title: from the abstract translation or AI re-rank, only when it is in the current output language.
  const target = data.language?.target;
  const absRes = data.ai.abstract_translation.result;
  const recAi = data.recommendation?.ai;
  const titleTr =
    (absRes && (!absRes.lang || absRes.lang === target) ? absRes.content.title || absRes.content.title_zh : null) ||
    (recAi && (!recAi.lang || recAi.lang === target) ? recAi.title_tr || recAi.title_zh : null);
  const venueSignal = data.recommendation?.breakdown.quality_signals.find((q) => q.key === "venue");
  const needsTranslation = data.language?.translate_needed ?? true;

  const tabs: { key: Tab; label: string; icon: React.ReactNode; st?: FeatureState }[] = [
    { key: "overview", label: t("pp.tab.overview"), icon: <LayoutGrid className="size-4" /> },
    { key: "fulltext", label: needsTranslation ? t("pp.tab.fulltext") : t("pp.tab.fulltext_only"), icon: <Languages className="size-4" />, st: data.ai.translate },
    { key: "summary", label: t("pp.tab.summary"), icon: <NotebookText className="size-4" />, st: data.ai.summary },
    { key: "modules", label: t("pp.tab.modules"), icon: <Layers className="size-4" />, st: data.ai.modules },
    { key: "contributions", label: t("pp.tab.contributions"), icon: <Lightbulb className="size-4" />, st: data.ai.contributions },
  ];

  const copyCitation = async (format: "bibtex" | "gbt7714") => {
    try {
      const c = await api.get<{ bibtex: string; gbt7714: string }>(`/papers/${p.id}/cite`);
      if (await copyText(c[format])) toast({ tone: "success", title: format === "bibtex" ? t("pp.copied_bibtex") : t("pp.copied_gbt") });
      else toast({ tone: "error", title: t("common.copy_failed"), description: t("common.clipboard_denied") });
    } catch (e) {
      toast({ tone: "error", title: t("common.copy_failed"), description: errorMessage(e) });
    }
  };

  return (
    <div className="mx-auto max-w-[1180px] px-4 pb-24 sm:px-6">
      {/* header */}
      <div className="pt-5 lg:pt-1">
        <div className="mb-4 flex items-center justify-between gap-2">
          <button onClick={() => (window.history.length > 1 ? navigate(-1) : navigate("/"))} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 -ml-2 text-[13px] text-text-2 hover:bg-surface-3 hover:text-text">
            <ArrowLeft className="size-4" /> {t("pp.back")}
          </button>
          <div className="flex items-center gap-1">
            {p.url && (
              <a href={p.url} target="_blank" rel="noreferrer">
                <Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />}>
                  <span className="hidden sm:inline">{t("pp.original")}</span>
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
              <span className="hidden sm:inline">{s.starred ? t("pp.starred") : t("paper.star")}</span>
            </Button>
            <Button size="sm" variant="ghost" icon={<Check className={cn("size-3.5", s.read && "text-success")} />} onClick={() => setState.mutate({ read: !s.read })}>
              <span className="hidden sm:inline">{s.read ? t("pp.read") : t("paper.mark_read")}</span>
            </Button>
            <Popover
              align="end"
              className="w-[220px]"
              trigger={({ toggle }) => <Button size="sm" variant="ghost" icon={<MoreHorizontal className="size-4" />} onClick={toggle} aria-label={t("pp.more")} />}
            >
              {(close) => (
                <>
                  <MenuItem icon={<Copy className="size-4" />} onClick={() => { close(); copyCitation("bibtex"); }}>
                    {t("pp.copy_bibtex")}
                  </MenuItem>
                  <MenuItem icon={<Quote className="size-4" />} onClick={() => { close(); copyCitation("gbt7714"); }}>
                    {t("pp.copy_gbt")}
                  </MenuItem>
                  <a href={`/api/papers/${p.id}/export?type=analysis`} onClick={close}>
                    <MenuItem icon={<Download className="size-4" />}>{t("pp.export_analysis")}</MenuItem>
                  </a>
                  <div className="my-1 border-t border-border" />
                  <MenuItem
                    icon={<EyeOff className="size-4" />}
                    onClick={() => {
                      close();
                      setState.mutate({ dismissed: !s.dismissed }, { onSuccess: () => toast({ tone: "success", title: s.dismissed ? t("pp.restored") : t("pp.dismissed") }) });
                    }}
                  >
                    {s.dismissed ? t("pp.restore") : t("pp.not_interested")}
                  </MenuItem>
                </>
              )}
            </Popover>
          </div>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2">
          {data.recommendation && <Badge tone="accent">{data.recommendation.direction_name}</Badge>}
          {data.recommendation?.breakdown.review && <Badge tone="success">{t("badge.survey")}</Badge>}
          {venueSignal && <Badge tone="warning">{venueSignal.short ?? venueSignal.label}</Badge>}
          <LanguageTag code={data.language?.fulltext ?? p.language} />
          {p.published && <span className="text-[13px] text-text-3">{t("pp.published_on", { date: longDate(p.published) })}</span>}
        </div>
        <h1 className="max-w-[920px] font-serif text-[26px] font-semibold leading-[1.25] tracking-[-0.01em] text-text sm:text-[30px]">
          <MathText text={p.title} />
        </h1>
        {titleTr && titleTr !== p.title && <p className="mt-2 max-w-[920px] text-[17px] text-text-2">{titleTr}</p>}
        <p className="mt-3 max-w-[920px] text-[14px] leading-relaxed text-text-2">
          {authorsOpen ? p.authors.join(", ") : authorsShort(p.authors, p.authors.length, 6)}
          {p.authors.length > 6 && (
            <button onClick={() => setAuthorsOpen(!authorsOpen)} className="ml-2 text-[13px] text-accent-text hover:underline">
              {authorsOpen ? t("pp.collapse") : t("pp.expand_all")}
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
            <AiPanel detail={data} kind="summary" state={data.ai.summary} icon={<NotebookText className="size-6" />} title={t("pp.summary.title")}
              description={t("pp.summary.desc")}
              outputs={[t("pp.summary.o1"), t("pp.summary.o2"), t("pp.summary.o3"), t("pp.summary.o4"), t("pp.summary.o5"), t("pp.summary.o6")]}>
              {(c) => <SummaryView c={c} />}
            </AiPanel>
          </div>
        )}
        {tab === "modules" && (
          <div className="mx-auto max-w-[960px]">
            <AiPanel detail={data} kind="modules" state={data.ai.modules} icon={<Layers className="size-6" />} title={t("pp.modules.title")}
              description={t("pp.modules.desc")}
              outputs={[t("pp.modules.o1"), t("pp.modules.o2"), t("pp.modules.o3"), t("pp.modules.o4"), t("pp.modules.o5"), t("pp.modules.o6")]}>
              {(c) => <ModulesView c={c} />}
            </AiPanel>
          </div>
        )}
        {tab === "contributions" && (
          <div className="mx-auto max-w-[960px]">
            <AiPanel detail={data} kind="contributions" state={data.ai.contributions} icon={<Lightbulb className="size-6" />} title={t("pp.contrib.title")}
              description={t("pp.contrib.desc")}
              outputs={[t("pp.contrib.o1"), t("pp.contrib.o2"), t("pp.contrib.o3"), t("pp.contrib.o4"), t("pp.contrib.o5"), t("pp.contrib.o6")]}>
              {(c) => <ContributionsView c={c} />}
            </AiPanel>
          </div>
        )}
      </div>
    </div>
  );
}
