import { getLang, joinList, locale, t } from "../i18n";

function parseDay(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function startOfToday() {
  const n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
}

function fmt(d: Date, opts: Intl.DateTimeFormatOptions): string {
  return new Intl.DateTimeFormat(locale(), opts).format(d);
}

/** ISO timestamp (UTC) -> local calendar day "YYYY-MM-DD". */
export function localDay(iso: string): string {
  const d = new Date(iso);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

export function daysAgo(day: string | null | undefined): number | null {
  if (!day) return null;
  const diff = Math.round((startOfToday().getTime() - parseDay(day).getTime()) / 86400000);
  return Math.max(0, diff);
}

export function relativeDay(day: string | null | undefined): string {
  const n = daysAgo(day);
  if (n === null) return t("date.unknown");
  if (n === 0) return t("date.today");
  if (n === 1) return t("date.yesterday");
  if (n < 7) return t("date.days_ago", { n });
  return shortDate(day!);
}

export function shortDate(day: string): string {
  const d = parseDay(day);
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return fmt(d, sameYear ? { month: "short", day: "numeric" } : { year: "numeric", month: "short", day: "numeric" });
}

export function longDate(day: string): string {
  return fmt(parseDay(day), { year: "numeric", month: "long", day: "numeric" });
}

export function todayHeading(): { date: string; weekday: string } {
  const d = new Date();
  return { date: fmt(d, { month: "long", day: "numeric" }), weekday: fmt(d, { weekday: "long" }) };
}

export function dayLabel(day: string): string {
  const n = daysAgo(day);
  const d = parseDay(day);
  const sameYear = d.getFullYear() === new Date().getFullYear();
  const base = fmt(d, sameYear ? { month: "long", day: "numeric", weekday: "long" } : { year: "numeric", month: "long", day: "numeric", weekday: "long" });
  if (n === 0) return `${t("date.today")} · ${base}`;
  if (n === 1) return `${t("date.yesterday")} · ${base}`;
  return base;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return t("date.just_now");
  if (s < 3600) return t("date.minutes_ago", { n: Math.floor(s / 60) });
  if (s < 86400) return t("date.hours_ago", { n: Math.floor(s / 3600) });
  if (s < 86400 * 7) return t("date.days_ago", { n: Math.floor(s / 86400) });
  return fmt(new Date(iso), { month: "short", day: "numeric" });
}

export function clockTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function tokens(n: number | undefined | null): string {
  const v = n ?? 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  const lang = getLang();
  if (v >= 10_000 && lang === "zh") return `${(v / 10_000).toFixed(1)} 万`;
  if (v >= 10_000 && lang === "ja") return `${(v / 10_000).toFixed(1)}万`;
  if (v >= 10_000 && lang === "ko") return `${(v / 10_000).toFixed(1)}만`;
  if (v >= 10_000) return `${(v / 1000).toFixed(1)}k`;
  return v.toLocaleString(locale());
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function authorsShort(authors: string[], total?: number, max = 3): string {
  if (!authors.length) return t("paper.authors_unknown");
  const n = total ?? authors.length;
  if (n <= max) return authors.join(", ");
  return t("paper.authors_etal", { names: authors.slice(0, max).join(", "), n });
}

export function pct(v: number) {
  return `${Math.round(v * 100)}`;
}

export function list(items: string[]): string {
  return joinList(items);
}

export const SOURCE_LABEL: Record<string, string> = {
  arxiv: "arXiv",
  openalex: "OpenAlex",
  cinii: "CiNii",
  semantic_scholar: "Semantic Scholar",
  pubmed: "PubMed",
};

/** Name of a paper language (ISO 639-1) in the interface language. */
export function languageName(code: string | null | undefined): string {
  if (!code) return "";
  try {
    return new Intl.DisplayNames([locale()], { type: "language" }).of(code) ?? code;
  } catch {
    return code;
  }
}
