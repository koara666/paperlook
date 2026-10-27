import { Award, Clock, Info, Target } from "lucide-react";
import type { Breakdown } from "../../api/types";
import { cn } from "../../lib/cn";
import { Popover } from "../ui/overlay";

export function ScoreRing({ score, size = 46 }: { score: number; size?: number }) {
  const v = Math.round(score * 100);
  const r = (size - 6) / 2;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={4} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="var(--accent)"
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - Math.min(1, score))}
          style={{ transition: "stroke-dashoffset .6s ease" }}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[13px] font-semibold tabular-nums text-text">{v}</span>
    </div>
  );
}

function Bar({ label, icon, value, weight, note }: { label: string; icon: React.ReactNode; value: number; weight: number; note?: string }) {
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[13px]">
        <span className="flex items-center gap-1.5 text-text-2">
          {icon}
          {label}
          {note && <span className="text-[11px] text-text-3">（{note}）</span>}
        </span>
        <span className="tabular-nums text-text">
          {Math.round(value * 100)}
          <span className="ml-1.5 text-[11px] text-text-3">×{Math.round(weight * 100)}%</span>
        </span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-surface-3">
        <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round(value * 100)}%`, opacity: 0.4 + weight }} />
      </div>
    </div>
  );
}

export function BreakdownPanel({ b, className }: { b: Breakdown; className?: string }) {
  const kw = [...b.matched.title.map((k) => ({ k, t: true })), ...b.matched.abstract.map((k) => ({ k, t: false }))];
  return (
    <div className={cn("space-y-3", className)}>
      <Bar label="研究相关度" icon={<Target className="size-3.5" />} value={b.relevance} weight={b.weights.relevance}
        note={b.ai_relevance != null ? "含 AI 精排" : undefined} />
      <Bar label="论文质量" icon={<Award className="size-3.5" />} value={b.quality} weight={b.weights.quality}
        note={b.quality_insufficient ? "依据不足，按中性值计" : b.quality_confidence < 0.5 ? "依据有限" : undefined} />
      <Bar label="时效性" icon={<Clock className="size-3.5" />} value={b.freshness} weight={b.weights.freshness} />
      {kw.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-medium text-text-3">命中关键词</div>
          <div className="flex flex-wrap gap-1">
            {kw.map(({ k, t }) => (
              <span key={k + t} className={cn("rounded px-1.5 py-0.5 text-xs", t ? "bg-accent-soft text-accent-text" : "bg-surface-3 text-text-2")}>
                {k}
                {t && <span className="ml-1 opacity-60">标题</span>}
              </span>
            ))}
          </div>
        </div>
      )}
      <div>
        <div className="mb-1 text-[11px] font-medium text-text-3">质量依据</div>
        {b.quality_signals.length ? (
          <ul className="space-y-0.5 text-[13px] text-text-2">
            {b.quality_signals.map((s) => (
              <li key={s.key} className="flex gap-1.5">
                <span className="text-text-3">•</span>
                <span>{s.label}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[13px] text-text-3">暂无可靠的质量信号（新论文通常还没有引用数据），不加分也不扣分。</p>
        )}
      </div>
    </div>
  );
}

export function ScoreWithBreakdown({ score, breakdown, size }: { score: number; breakdown: Breakdown; size?: number }) {
  return (
    <Popover
      align="end"
      className="w-[300px] p-4"
      trigger={({ toggle }) => (
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            toggle();
          }}
          className="relative z-10 rounded-full transition-transform hover:scale-105"
          aria-label="查看评分构成"
          title="推荐评分（点击查看构成）"
        >
          <ScoreRing score={score} size={size} />
        </button>
      )}
    >
      <div onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-baseline justify-between">
          <span className="text-sm font-semibold text-text">推荐评分</span>
          <span className="text-lg font-semibold tabular-nums text-text">
            {Math.round(score * 100)}
            <span className="text-xs font-normal text-text-3"> / 100</span>
          </span>
        </div>
        <BreakdownPanel b={breakdown} />
        <p className="mt-3 flex gap-1.5 border-t border-border pt-2.5 text-[11px] leading-relaxed text-text-3">
          <Info className="mt-px size-3 shrink-0" />
          综合评分 = 各分项 × 权重之和。权重可在「设置 → 推荐设置」中调整。
        </p>
      </div>
    </Popover>
  );
}
