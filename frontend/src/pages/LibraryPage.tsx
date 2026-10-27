import { Archive, CalendarDays, Search, Star } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useHistory, useLibrary, usePaperState } from "../api/hooks";
import type { AiStatusSummary, PaperCard } from "../api/types";
import { AiBadges } from "../components/papers/PaperCard";
import { ScoreRing } from "../components/papers/Score";
import { Badge, Button, Card, EmptyState, Input, Segmented, Skeleton } from "../components/ui/primitives";
import { cn } from "../lib/cn";
import { SOURCE_LABEL, authorsShort, dayLabel, relativeDay } from "../lib/format";
import { MathText } from "../lib/math";

type Filter = "history" | "all" | "starred" | "unread" | "analyzed" | "dismissed";

function Row({ paper, score, direction, ai, titleZh }: { paper: PaperCard; score?: number; direction?: string; ai: AiStatusSummary; titleZh?: string }) {
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
        {titleZh && <div className="mt-0.5 truncate text-[13px] text-text-2">{titleZh}</div>}
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-3">
          {direction && <Badge tone="accent">{direction}</Badge>}
          <span>{relativeDay(paper.published)}</span>
          <span>·</span>
          <span>{paper.sources.map((s) => SOURCE_LABEL[s] ?? s).join(" · ")}</span>
          <span className="hidden sm:inline">·</span>
          <span className="hidden max-w-[260px] truncate sm:inline">{authorsShort(paper.authors, paper.author_count, 2)}</span>
          <AiBadges s={ai} className="ml-1" />
        </div>
      </div>
      <div className="relative z-10 flex shrink-0 items-center gap-2">
        <button
          onClick={() => setState.mutate({ starred: !paper.state.starred })}
          className={cn("rounded-lg p-1.5 transition-opacity hover:bg-surface-3", paper.state.starred ? "opacity-100" : "opacity-0 group-hover:opacity-100 max-sm:opacity-100")}
          aria-label={paper.state.starred ? "取消收藏" : "收藏"}
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
        <EmptyState icon={<CalendarDays className="size-6" />} title="还没有推荐记录" description="在「今日推荐」中获取推荐后，历史记录会按日期出现在这里。"
          action={<Link to="/"><Button variant="primary">去获取推荐</Button></Link>} />
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
                {items.length} 篇 · 已读 {items.filter((i) => i.paper.state.read).length}
              </span>
            </div>
            <Card className="divide-y divide-border overflow-hidden">
              {items.map((it) => (
                <Row key={it.rec_id} paper={it.paper} score={it.score} direction={it.direction_name} ai={it.ai_status} titleZh={it.ai?.title_zh} />
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
      all: { t: "论文库是空的", d: "推荐过的论文会自动保存在这里。" },
      starred: { t: "还没有收藏的论文", d: "在论文卡片或详情页点击星标即可收藏。" },
      unread: { t: "全部读完了", d: "没有未读的论文。" },
      analyzed: { t: "还没有 AI 分析过的论文", d: "在论文详情页使用翻译、总结等功能后会出现在这里。" },
      dismissed: { t: "没有隐藏的论文", d: "标记为「不感兴趣」的论文会出现在这里，可以随时恢复。" },
    };
    const m = q ? { t: "没有找到匹配的论文", d: `没有标题、摘要或作者包含「${q}」的论文。` } : map[filter];
    return (
      <Card>
        <EmptyState icon={filter === "starred" ? <Star className="size-6" /> : <Archive className="size-6" />} title={m.t} description={m.d} />
      </Card>
    );
  }
  return (
    <div>
      <div className="mb-2.5 px-1 text-xs text-text-3">共 {data.total} 篇</div>
      <Card className="divide-y divide-border overflow-hidden">
        {data.items.map((it) => (
          <Row key={it.paper.id} paper={it.paper} score={it.recommendation?.score} direction={it.recommendation?.direction_name} ai={it.ai_status}
            titleZh={it.recommendation?.ai?.title_zh} />
        ))}
      </Card>
      {data.total > data.items.length && (
        <div className="mt-4 text-center">
          <Button loading={isFetching} onClick={() => setLimit(limit + 30)}>
            加载更多
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
    const t = setTimeout(() => setDebounced(q.trim()), 300);
    return () => clearTimeout(t);
  }, [q]);
  const effective: Filter = debounced && filter === "history" ? "all" : filter;

  return (
    <div className="mx-auto max-w-[920px] px-4 pb-20 pt-6 sm:px-6 lg:pt-10">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-[28px] font-semibold tracking-tight text-text">论文库</h1>
          <p className="mt-1 text-sm text-text-2">所有推荐过的论文、阅读记录与 AI 分析结果都保存在本机。</p>
        </div>
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-3" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="搜索标题、摘要、作者…" className="pl-9" />
        </div>
      </div>
      <div className="mb-5 overflow-x-auto">
        <Segmented<Filter>
          value={effective}
          onChange={(v) => setParams(v === "history" ? {} : { f: v })}
          options={[
            { value: "history", label: "按日期" },
            { value: "all", label: "全部" },
            { value: "starred", label: "收藏" },
            { value: "unread", label: "未读" },
            { value: "analyzed", label: "已分析" },
            { value: "dismissed", label: "已隐藏" },
          ]}
        />
      </div>
      {effective === "history" ? <HistoryView /> : <ListView filter={effective} q={debounced} />}
    </div>
  );
}
