import { Award, Clock, Info, Target } from "lucide-react";
import type { Breakdown } from "../../api/types";
import { t } from "../../i18n";
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
          {note && <span className="text-[11px] text-text-3">{t("score.note", { note })}</span>}
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

const KINDS = ["starred", "noted", "analyzed", "opened", "dismissed"] as const;

function PreferenceLine({ p }: { p: NonNullable<Breakdown["preference"]> }) {
  const pts = Math.round(p.adjust * 100);
  const up = p.adjust > 0;
  const kind = (KINDS as readonly string[]).includes(p.kind ?? "") ? (p.kind as (typeof KINDS)[number]) : "opened";
  const why = p.title && p.kind && Math.abs(p.adjust) >= 0.03
    ? (kind === "dismissed" ? t("score.pref_dismissed", { title: p.title }) : t("score.pref_similar", { title: p.title, kind: t(`score.kind.${kind}`) }))
    : up ? t("score.pref_closer") : t("score.pref_weaker");
  return (
    <p className="mt-1 flex gap-1 text-[12px] leading-snug text-text-3">
      <span className={cn("shrink-0 tabular-nums font-medium", up ? "text-success" : "text-text-2")}>
        {t("score.by_feedback")} {up ? "+" : pts === 0 ? "±" : "−"}{Math.abs(pts)}
      </span>
      <span className="min-w-0 truncate" title={why}>· {why}</span>
    </p>
  );
}

export function BreakdownPanel({ b, className }: { b: Breakdown; className?: string }) {
  const kw = [...b.matched.title.map((k) => ({ k, inTitle: true })), ...b.matched.abstract.map((k) => ({ k, inTitle: false }))];
  return (
    <div className={cn("space-y-3", className)}>
      <div>
        <Bar label={t("score.relevance")} icon={<Target className="size-3.5" />} value={b.relevance} weight={b.weights.relevance}
          note={b.ai_relevance != null ? t("score.with_ai") : undefined} />
        {b.preference && Math.abs(b.preference.adjust) >= 0.005 && <PreferenceLine p={b.preference} />}
      </div>
      <Bar label={t("score.quality")} icon={<Award className="size-3.5" />} value={b.quality} weight={b.weights.quality}
        note={b.quality_insufficient ? t("score.insufficient") : b.quality_confidence < 0.5 ? t("score.limited") : undefined} />
      <Bar label={t("score.freshness")} icon={<Clock className="size-3.5" />} value={b.freshness} weight={b.weights.freshness} />
      {(b.field_mismatch || b.minor || b.review_bonus) && (
        <ul className="space-y-0.5 text-[12px] leading-snug text-text-3">
          {b.review_bonus ? <li>{t("score.review_bonus")}</li> : null}
          {b.field_mismatch ? <li>{t("score.field_mismatch")}</li> : null}
          {b.minor ? <li>{t("score.minor")}</li> : null}
        </ul>
      )}
      {kw.length > 0 && (
        <div>
          <div className="mb-1 text-[11px] font-medium text-text-3">{t("score.matched")}</div>
          <div className="flex flex-wrap gap-1">
            {kw.map(({ k, inTitle }) => (
              <span key={k + inTitle} className={cn("rounded px-1.5 py-0.5 text-xs", inTitle ? "bg-accent-soft text-accent-text" : "bg-surface-3 text-text-2")}>
                {k}
                {inTitle && <span className="ml-1 opacity-60">{t("score.in_title")}</span>}
              </span>
            ))}
          </div>
        </div>
      )}
      <div>
        <div className="mb-1 text-[11px] font-medium text-text-3">{t("score.quality_basis")}</div>
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
          <p className="text-[13px] text-text-3">{t("score.no_signals")}</p>
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
          aria-label={t("score.view")}
          title={t("score.title_tip")}
        >
          <ScoreRing score={score} size={size} />
        </button>
      )}
    >
      <div onClick={(e) => e.stopPropagation()}>
        <div className="mb-3 flex items-baseline justify-between">
          <span className="text-sm font-semibold text-text">{t("score.title")}</span>
          <span className="text-lg font-semibold tabular-nums text-text">
            {Math.round(score * 100)}
            <span className="text-xs font-normal text-text-3"> / 100</span>
          </span>
        </div>
        <BreakdownPanel b={breakdown} />
        <p className="mt-3 flex gap-1.5 border-t border-border pt-2.5 text-[11px] leading-relaxed text-text-3">
          <Info className="mt-px size-3 shrink-0" />
          {t("score.formula")}
        </p>
      </div>
    </Popover>
  );
}
