/**
 * Interface language (中文 / English / 日本語 / 한국어).
 *
 *   const t = useT();  t("nav.today")  t("today.count", { n: 5 })
 *   rich("onboarding.ai_hint", {}, { a: (s) => <Link …>{s}</Link> })   // "<a>…</a>" in the text
 *
 * The language is kept in the backend settings (so backend messages follow it) and in localStorage (so the
 * first paint is already right). Changing it remounts the app (every text re-renders) and refetches all
 * queries, because the backend renders its own messages in the chosen language. English texts may use
 * "singular|plural" with an `n` parameter.
 */
import { useQueryClient } from "@tanstack/react-query";
import { createContext, Fragment, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "../api/client";
import en from "./en";
import ja from "./ja";
import ko from "./ko";
import zh from "./zh";

export type Lang = "zh" | "en" | "ja" | "ko";
export type MsgKey = keyof typeof zh;
export type Params = Record<string, string | number | null | undefined>;

export const LANGUAGES: { code: Lang; native: string; short: string; locale: string }[] = [
  { code: "zh", native: "简体中文", short: "中文", locale: "zh-CN" },
  { code: "en", native: "English", short: "EN", locale: "en-US" },
  { code: "ja", native: "日本語", short: "日本語", locale: "ja-JP" },
  { code: "ko", native: "한국어", short: "한국어", locale: "ko-KR" },
];

const DICTS: Record<Lang, Record<MsgKey, string>> = { zh, en, ja, ko };
const STORAGE_KEY = "pl-lang";

export function normalizeLang(v: string | null | undefined): Lang | null {
  const s = (v ?? "").toLowerCase();
  if (s.startsWith("zh")) return "zh";
  const c = s.slice(0, 2);
  return c === "en" || c === "ja" || c === "ko" ? c : null;
}

/** The browser's / operating system's preferred language among the supported ones. */
export function detectLang(): Lang {
  const prefs = typeof navigator !== "undefined" ? [...(navigator.languages ?? []), navigator.language] : [];
  for (const p of prefs) {
    const l = normalizeLang(p);
    if (l) return l;
  }
  return "en";
}

function initialLang(): Lang {
  try {
    const stored = normalizeLang(localStorage.getItem(STORAGE_KEY));
    if (stored) return stored;
  } catch {
    /* storage unavailable */
  }
  return detectLang();
}

let current: Lang = initialLang();

export function getLang(): Lang {
  return current;
}

/** BCP 47 locale for Intl formatting. */
export function locale(lang: Lang = current): string {
  return LANGUAGES.find((l) => l.code === lang)?.locale ?? "en-US";
}

function applyDocumentLang(lang: Lang) {
  if (typeof document !== "undefined") document.documentElement.lang = locale(lang);
}
applyDocumentLang(current);

export function t(key: MsgKey, params?: Params): string {
  let s: string = DICTS[current][key] ?? zh[key] ?? key;
  if (current === "en" && s.includes("|") && params && params.n !== undefined) {
    const [one, other] = s.split("|");
    s = String(params.n) === "1" ? one : other ?? one;
  }
  if (params) s = s.replace(/\{(\w+)\}/g, (m, k) => (params[k] !== undefined && params[k] !== null ? String(params[k]) : m));
  return s;
}

/** Text with inline markup: tags such as <a>…</a> or <b>…</b> are rendered by the given functions. */
export function rich(key: MsgKey, params: Params, tags: Record<string, (chunk: string) => ReactNode>): ReactNode {
  const s = t(key, params);
  const out: ReactNode[] = [];
  const re = /<(\w+)>(.*?)<\/\1>/g;
  let last = 0;
  let i = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    if (m.index > last) out.push(s.slice(last, m.index));
    const render = tags[m[1]];
    out.push(<Fragment key={i++}>{render ? render(m[2]) : m[2]}</Fragment>);
    last = re.lastIndex;
  }
  if (last < s.length) out.push(s.slice(last));
  return out;
}

/** Capitalises the first letter (English feature names are lower-case inside sentences). */
export function cap(s: string): string {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
}

/** Joins items with the language's list separator (、 in Chinese and Japanese). */
export function joinList(items: string[]): string {
  return items.join(current === "zh" || current === "ja" ? "、" : ", ");
}

interface Ctx {
  lang: Lang;
  setLang: (l: Lang) => void;
}

const I18nCtx = createContext<Ctx>({ lang: current, setLang: () => {} });

export function I18nProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const [lang, setState] = useState<Lang>(current);

  const activate = useCallback((l: Lang) => {
    current = l;
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* ignore */
    }
    applyDocumentLang(l);
    setState(l);
  }, []);

  const setLang = useCallback(
    (l: Lang) => {
      if (l === current) return;
      activate(l);
      // The backend renders recommendation reasons, errors, source descriptions … in this language.
      api
        .patch("/settings", { language: l })
        .catch(() => undefined)
        .finally(() => qc.invalidateQueries());
    },
    [activate, qc],
  );

  // Follow the saved setting; save the detected language the first time.
  useEffect(() => {
    let cancelled = false;
    api
      .get<{ language: string }>("/settings")
      .then((s) => {
        if (cancelled) return;
        const saved = normalizeLang(s.language);
        if (saved && saved !== current) {
          activate(saved);
          qc.invalidateQueries();
        } else if (!saved) {
          api.patch("/settings", { language: current }).then(() => qc.invalidateQueries()).catch(() => undefined);
        }
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [activate, qc]);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return (
    <I18nCtx.Provider value={value}>
      <Fragment key={lang}>{children}</Fragment>
    </I18nCtx.Provider>
  );
}

export function useLang() {
  return useContext(I18nCtx);
}

/** `t` bound to the current language (components re-render when it changes). */
export function useT() {
  useContext(I18nCtx);
  return t;
}
