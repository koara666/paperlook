const WEEK = ["星期日", "星期一", "星期二", "星期三", "星期四", "星期五", "星期六"];

function parseDay(s: string): Date {
  const [y, m, d] = s.slice(0, 10).split("-").map(Number);
  return new Date(y, (m || 1) - 1, d || 1);
}

function startOfToday() {
  const n = new Date();
  return new Date(n.getFullYear(), n.getMonth(), n.getDate());
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
  if (n === null) return "日期未知";
  if (n === 0) return "今天";
  if (n === 1) return "昨天";
  if (n < 7) return `${n} 天前`;
  return shortDate(day!);
}

export function shortDate(day: string): string {
  const d = parseDay(day);
  const sameYear = d.getFullYear() === new Date().getFullYear();
  return sameYear ? `${d.getMonth() + 1}月${d.getDate()}日` : `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

export function longDate(day: string): string {
  const d = parseDay(day);
  return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
}

export function todayHeading(): { date: string; weekday: string } {
  const d = new Date();
  return { date: `${d.getMonth() + 1}月${d.getDate()}日`, weekday: WEEK[d.getDay()] };
}

export function dayLabel(day: string): string {
  const n = daysAgo(day);
  const d = parseDay(day);
  const base = `${d.getMonth() + 1}月${d.getDate()}日 ${WEEK[d.getDay()]}`;
  if (n === 0) return `今天 · ${base}`;
  if (n === 1) return `昨天 · ${base}`;
  return d.getFullYear() === new Date().getFullYear() ? base : `${d.getFullYear()}年${base}`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  const s = Math.max(0, (Date.now() - t) / 1000);
  if (s < 60) return "刚刚";
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`;
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`;
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} 天前`;
  const d = new Date(iso);
  return `${d.getMonth() + 1}月${d.getDate()}日`;
}

export function clockTime(iso: string): string {
  const d = new Date(iso);
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
}

export function tokens(n: number | undefined | null): string {
  const v = n ?? 0;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`;
  if (v >= 10_000) return `${(v / 10_000).toFixed(1)} 万`;
  return v.toLocaleString("zh-CN");
}

export function bytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 ** 2).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}

export function authorsShort(authors: string[], total?: number, max = 3): string {
  if (!authors.length) return "作者未知";
  const n = total ?? authors.length;
  if (n <= max) return authors.join(", ");
  return `${authors.slice(0, max).join(", ")} 等 ${n} 人`;
}

export function pct(v: number) {
  return `${Math.round(v * 100)}`;
}

export const SOURCE_LABEL: Record<string, string> = {
  arxiv: "arXiv",
  openalex: "OpenAlex",
  semantic_scholar: "Semantic Scholar",
  pubmed: "PubMed",
};
