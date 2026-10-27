import { Award, Check, Code2, EyeOff, Flame, Languages, Layers, Lightbulb, NotebookText, Sparkles, Star } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { usePaperState } from "../../api/hooks";
import type { AiStatusSummary, Breakdown, PaperCard as Card, RecAI } from "../../api/types";
import { cn } from "../../lib/cn";
import { SOURCE_LABEL, authorsShort, relativeDay } from "../../lib/format";
import { MathText } from "../../lib/math";
import { useToast } from "../ui/overlay";
import { Badge, IconButton } from "../ui/primitives";
import { ScoreWithBreakdown } from "./Score";

export function AiBadges({ s, className }: { s: AiStatusSummary; className?: string }) {
  const items: { key: string; icon: ReactNode; label: string }[] = [];
  if (s.summary) items.push({ key: "s", icon: <NotebookText className="size-3" />, label: "总结" });
  if (s.modules) items.push({ key: "m", icon: <Layers className="size-3" />, label: "模块" });
  if (s.contributions) items.push({ key: "c", icon: <Lightbulb className="size-3" />, label: "创新点" });
  if (s.translation_units) items.push({ key: "t", icon: <Languages className="size-3" />, label: "已翻译" });
  if (!items.length) return null;
  return (
    <div className={cn("flex flex-wrap items-center gap-1", className)}>
      {items.map((i) => (
        <span key={i.key} className="inline-flex h-5 items-center gap-1 rounded-md bg-success-soft px-1.5 text-[11px] font-medium text-success">
          {i.icon}
          {i.label}
        </span>
      ))}
    </div>
  );
}

function signalIcon(key: string) {
  if (key === "venue") return <Award className="size-3" />;
  if (key === "community") return <Flame className="size-3" />;
  if (key === "completeness") return <Code2 className="size-3" />;
  return <Award className="size-3" />;
}

export function PaperCardView({
  paper,
  score,
  breakdown,
  direction,
  ai,
  aiStatus,
  index,
}: {
  paper: Card;
  score?: number;
  breakdown?: Breakdown;
  direction?: string;
  ai?: RecAI | null;
  aiStatus?: AiStatusSummary;
  index?: number;
}) {
  const setState = usePaperState(paper.id);
  const toast = useToast();
  const read = paper.state.read;
  const kws = breakdown ? [...breakdown.matched.title, ...breakdown.matched.abstract.filter((k) => !breakdown.matched.title.includes(k))] : [];

  const act = (e: React.MouseEvent, patch: Record<string, boolean>, msg?: string) => {
    e.preventDefault();
    e.stopPropagation();
    setState.mutate(patch, { onSuccess: () => msg && toast({ tone: "success", title: msg }) });
  };

  return (
    <article
      className={cn(
        "group relative rounded-2xl border border-border bg-surface p-4 shadow-soft transition-all duration-200 hover:border-border-strong hover:shadow-card sm:p-5",
        "animate-fade-in",
      )}
      style={index !== undefined ? { animationDelay: `${Math.min(index, 10) * 40}ms` } : undefined}
    >
      <div className="flex gap-4">
        <div className="min-w-0 flex-1">
          {/* meta row */}
          <div className="mb-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-text-3">
            {direction && <Badge tone="accent">{direction}</Badge>}
            <span>{paper.sources.map((s) => SOURCE_LABEL[s] ?? s).join(" · ")}</span>
            <span className="text-border-strong">/</span>
            <span title={paper.published ?? undefined}>
              {relativeDay(paper.published)}
              {paper.date_quality === "approx" && "（约）"}
            </span>
            {paper.venue && (
              <>
                <span className="text-border-strong">/</span>
                <span className="max-w-[220px] truncate">{paper.venue}</span>
              </>
            )}
          </div>

          {/* title */}
          <h2 className="pr-1 font-serif text-[18px] font-semibold leading-snug tracking-[-0.005em] sm:text-[19px]">
            <Link
              to={`/paper/${paper.id}`}
              className={cn("outline-none after:absolute after:inset-0 after:rounded-2xl", read ? "text-text-2" : "text-text")}
            >
              {!read && <span className="mb-[3px] mr-2 inline-block size-2 rounded-full bg-accent align-middle" title="未读" />}
              <MathText text={paper.title} />
            </Link>
          </h2>
          {ai?.title_zh && <p className="mt-1 text-[14px] text-text-2">{ai.title_zh}</p>}
          <p className="mt-1.5 truncate text-[13px] text-text-3">{authorsShort(paper.authors, paper.author_count)}</p>

          {/* summary */}
          {ai?.tldr ? (
            <p className="mt-2.5 flex gap-1.5 text-[14px] leading-relaxed text-text-2">
              <Sparkles className="mt-1 size-3.5 shrink-0 text-accent" />
              <span>{ai.tldr}</span>
            </p>
          ) : (
            paper.abstract && (
              <p className="mt-2.5 line-clamp-2 text-[14px] leading-relaxed text-text-2">
                <MathText text={paper.abstract} />
              </p>
            )
          )}

          {/* why recommended */}
          {(kws.length > 0 || breakdown?.quality_signals.length || ai?.reason) && (
            <div className="mt-3 flex flex-wrap items-center gap-1.5">
              {kws.slice(0, 4).map((k) => (
                <span key={k} className="inline-flex h-[22px] items-center rounded-md border border-border px-1.5 text-xs text-text-2">
                  {k}
                </span>
              ))}
              {breakdown?.quality_signals.slice(0, 3).map((s) => (
                <span key={s.key} className="inline-flex h-[22px] items-center gap-1 rounded-md bg-warning-soft px-1.5 text-xs text-warning">
                  {signalIcon(s.key)}
                  {s.label.replace("作者注明：", "")}
                </span>
              ))}
            </div>
          )}
        </div>

        {score !== undefined && breakdown && (
          <div className="shrink-0">
            <ScoreWithBreakdown score={score} breakdown={breakdown} />
          </div>
        )}
      </div>

      {/* footer */}
      <div className="relative z-10 mt-3 flex items-center justify-between gap-2 border-t border-border pt-3">
        <AiBadges s={aiStatus ?? {}} />
        <div className="ml-auto flex items-center gap-0.5 opacity-100 transition-opacity sm:opacity-60 sm:group-hover:opacity-100">
          <IconButton label={paper.state.starred ? "取消收藏" : "收藏"} active={paper.state.starred}
            onClick={(e) => act(e, { starred: !paper.state.starred }, paper.state.starred ? undefined : "已加入收藏")}>
            <Star className={cn("size-4", paper.state.starred && "fill-current text-[#e9a93a]")} />
          </IconButton>
          <IconButton label={read ? "标为未读" : "标为已读"} active={read} onClick={(e) => act(e, { read: !read })}>
            <Check className="size-4" />
          </IconButton>
          <IconButton label="不感兴趣（不再显示）" onClick={(e) => act(e, { dismissed: true }, "已隐藏，可在论文库中找回")}>
            <EyeOff className="size-4" />
          </IconButton>
        </div>
      </div>
    </article>
  );
}
