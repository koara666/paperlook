import { Archive, CalendarDays, Download, NotebookPen, Search, Star } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useHistory, useLibrary, usePaperState } from "../api/hooks";
import type { AiStatusSummary, PaperCard, RecAI } from "../api/types";
import { AiBadges, LanguageTag } from "../components/papers/PaperCard";
import { ScoreRing } from "../components/papers/Score";
import { Badge, Button, Card, EmptyState, Input, Segmented, Skeleton } from "../components/ui/primitives";
import { getLang, t } from "../i18n";
import { cn } from "../lib/cn";
import { SOURCE_LABEL, authorsShort, dayLabel, relativeDay } from "../lib/format";
import { MathText } from "../lib/math";

type Filter = "history" | "all" | "starred" | "noted" | "unread" | "analyzed" | "dismissed";

function aiTitle(ai: RecAI | null | undefined): string | undefined {
  if (!ai || (ai.lang && ai.lang !== getLang())) return undefined;
  return ai.title_tr || ai.title_zh || undefined;
}

function Row({ paper, score, direction, ai, titleTr }: { paper: PaperCard; score?: number; direction?: string; ai: AiStatusSummary; titleTr?: string }) {
  const setState = usePaperState(paper.id);
  return (
    <div className="group relative flex items-start gap-4 px-4 py-4 transition-colors hover:bg-surface-2 sm:px-5">
      <div className="min-w-0 flex-1">
        <Link to={`/paper/${paper.id}`} className="font-serif text-[16.5px] font-semibold leading-snug after:absolute after:inset-0">
          {!paper.state.read && <span className="mb-[3px] mr-2 inline-block size-1.5 rounded-full bg-accent align-middle" />}
          <span className={paper.state.read ? "text-text-2" : "text-text"}>
            <MathText text={paper.title} />
          </span>
        </Link>
        {titleTr && titleTr !== paper.title && <div className="mt-0.5 truncate text-[13px] text-text-2">{titleTr}</div>}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-3">
          {direction && <Badge tone="accent">{direction}</Badge>}
          <LanguageTag code={paper.language} />
          <span>{relativeDay(paper.published)}</span>
          <span>·</span>
          <span>{paper.sources.map((s) => SOURCE_LABEL[s] ?? s).join(" · ")}</span>
          <span className="hidden sm:inline">·</span>
          <span className="hidden max-w-[260px] truncate sm:inline">{authorsShort(paper.authors, paper.author_count, 2)}</span>
          <AiBadges s={ai} className="ml-1" />
        </div>
        {paper.state.note?.trim() && (
          <div className="mt-1.5 flex items-start gap-1.5 text-[13px] text-text-2">
            <NotebookPen className="mt-[3px] size-3.5 shrink-0 text-text-3" />
            <span className="line-clamp-1">
              <MathText text={paper.state.note.trim()} />
            </span>
          </div>
        )}
      </div>
      <div className="relative z-10 flex shrink-0 items-center gap-2">
        <button
          onClick={() => setState.mutate({ starred: !paper.state.starred })}
          className={cn("rounded-lg p-1.5 transition-opacity hover:bg-surface-3", paper.state.starred ? "opacity-100" : "opacity-0 group-hover:opacity-100 max-sm:opacity-100")}
          aria-label={paper.state.starred ? t("paper.unstar") : t("paper.star")}
        >
          <Star className={cn("size-4", paper.state.starred ? "fill-current text-[#e9a93a]" : "text-text-3")} />
        </button>
        {score !== undefined && <ScoreRing score={score} size={36} />}
      </div>
    </div>
  );
}

function HistoryView() {
  const { data, isLoading } = useHistory();
  if (isLoading) return <Skeleton className="h-64 rounded-2xl" />;
  if (!data?.length)
    return (
      <Card>
        <EmptyState icon={<CalendarDays className="size-6" />} title={t("lib.empty.history")} description={t("lib.empty.history_desc")}
          action={<Link to="/"><Button variant="primary">{t("lib.go_fetch")}</Button></Link>} />
      </Card>
    );
  return (
    <div className="space-y-8">
      {data.map((d) => {
        const items = d.items.filter((i) => !i.paper.state.dismissed);
        if (!items.length) return null;
        return (
          <section key={d.day}>
            <div className="mb-2.5 flex items-baseline justify-between px-1">
              <h2 className="text-sm font-semibold text-text">{dayLabel(d.day)}</h2>
              <span className="text-xs text-text-3">
                {t("lib.day_count", { n: items.length, read: items.filter((i) => i.paper.state.read).length })}
              </span>
            </div>
            <Card className="divide-y divide-border overflow-hidden">
              {items.map((it) => (
                <Row key={it.rec_id} paper={it.paper} score={it.score} direction={it.direction_name} ai={it.ai_status} titleTr={aiTitle(it.ai)} />
              ))}
            </Card>
          </section>
        );
      })}
    </div>
  );
}

function ListView({ filter, q }: { filter: Exclude<Filter, "history">; q: string }) {
  const [limit, setLimit] = useState(30);
  useEffect(() => setLimit(30), [filter, q]);
  const { data, isLoading, isFetching } = useLibrary(filter, q, limit);
  if (isLoading) return <Skeleton className="h-64 rounded-2xl" />;
  if (!data?.items.length) {
    const map: Record<string, { t: string; d: string }> = {
      all: { t: t("lib.empty.all"), d: t("lib.empty.all_desc") },
      starred: { t: t("lib.empty.starred"), d: t("lib.empty.starred_desc") },
      noted: { t: t("lib.empty.noted"), d: t("lib.empty.noted_desc") },
      unread: { t: t("lib.empty.unread"), d: t("lib.empty.unread_desc") },
      analyzed: { t: t("lib.empty.analyzed"), d: t("lib.empty.analyzed_desc") },
      dismissed: { t: t("lib.empty.dismissed"), d: t("lib.empty.dismissed_desc") },
    };
    const m = q ? { t: t("lib.empty.search"), d: t("lib.empty.search_desc", { q }) } : map[filter];
    return (
      <Card>
        <EmptyState icon={filter === "starred" ? <Star className="size-6" /> : filter === "noted" ? <NotebookPen className="size-6" /> : <Archive className="size-6" />}
          title={m.t} description={m.d} />
      </Card>
    );
  }
  return (
    <div>
      <div className="mb-2 flex items-center justify-between px-1">
        <span className="text-xs text-text-3">{t("lib.total", { n: data.total })}</span>
        <a href={`/api/library/bibtex?${new URLSearchParams({ filter, q })}`}>
          <Button size="xs" variant="ghost" icon={<Download className="size-3.5" />}>
            {t("lib.export_bib")}
          </Button>
        </a>
      </div>
      <Card className="divide-y divide-border overflow-hidden">
        {data.items.map((it) => (
          <Row key={it.paper.id} paper={it.paper} score={it.recommendation?.score} direction={it.recommendation?.direction_name} ai={it.ai_status}
            titleTr={aiTitle(it.recommendation?.ai)} />
        ))}
      </Card>
      {data.total > data.items.length && (
        <div className="mt-4 text-center">
          <Button loading={isFetching} onClick={() => setLimit(limit + 30)}>
            {t("lib.load_more")}
          </Button>
        </div>
      )}
    </div>
  );
}

export default function LibraryPage() {
  const [params, setParams] = useSearchParams();
  const filter = (params.get("f") as Filter) || "history";
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(q.trim()), 300);
    return () => clearTimeout(timer);
  }, [q]);
  const effective: Filter = debounced && filter === "history" ? "all" : filter;

  return (
    <div className="mx-auto max-w-[920px] px-4 pb-20 pt-6 sm:px-6 lg:pt-2">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-[28px] font-semibold tracking-tight text-text">{t("nav.library")}</h1>
          <p className="mt-1 text-sm text-text-2">{t("lib.subtitle")}</p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-3" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("lib.search")} className="pl-9" />
        </div>
      </div>
      <div className="mb-5 overflow-x-auto">
        <Segmented<Filter>
          value={effective}
          onChange={(v) => setParams(v === "history" ? {} : { f: v })}
          options={[
            { value: "history", label: t("lib.f.history") },
            { value: "all", label: t("lib.f.all") },
            { value: "starred", label: t("lib.f.starred") },
            { value: "noted", label: t("lib.f.noted") },
            { value: "unread", label: t("lib.f.unread") },
            { value: "analyzed", label: t("lib.f.analyzed") },
            { value: "dismissed", label: t("lib.f.dismissed") },
          ]}
        />
      </div>
      {effective === "history" ? <HistoryView /> : <ListView filter={effective} q={debounced} />}
    </div>
  );
}
