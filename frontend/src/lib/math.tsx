import katex from "katex";
import { memo, useMemo } from "react";

type Token = { t: "text" | "math" | "dmath"; v: string };

const MACROS: Record<string, string> = {
  "\\bm": "\\boldsymbol{#1}",
  "\\mathbbm": "\\mathbb{#1}",
  "\\textsc": "\\text{#1}",
  "\\textup": "\\text{#1}",
  "\\mathds": "\\mathbb{#1}",
  "\\coloneqq": "\\mathrel{\\vcenter{:}}=",
  "\\eqqcolon": "=\\mathrel{\\vcenter{:}}",
  "\\bigtimes": "\\times",
};

const cache = new Map<string, string>();

export function renderLatex(src: string, display: boolean): string {
  const key = (display ? "D" : "I") + src;
  const hit = cache.get(key);
  if (hit !== undefined) return hit;
  let html: string;
  try {
    html = katex.renderToString(src, {
      displayMode: display,
      throwOnError: false,
      strict: "ignore",
      output: "html",
      macros: { ...MACROS },
      errorColor: "currentColor",
      trust: false,
    });
  } catch {
    html = `<code>${escapeHtml(src)}</code>`;
  }
  if (cache.size > 5000) cache.clear();
  cache.set(key, html);
  return html;
}

function escapeHtml(s: string) {
  return s.replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]!);
}

/** Split text containing $inline$ / $$display$$ math (and \$ literal dollars). */
export function tokenize(text: string): Token[] {
  const out: Token[] = [];
  let buf = "";
  let i = 0;
  while (i < text.length) {
    const ch = text[i];
    if (ch === "\\" && text[i + 1] === "$") {
      buf += "$";
      i += 2;
      continue;
    }
    if (ch === "$") {
      const display = text[i + 1] === "$";
      const open = display ? 2 : 1;
      let j = i + open;
      let found = -1;
      while (j < text.length) {
        if (text[j] === "\\") {
          j += 2;
          continue;
        }
        if (text[j] === "$" && (!display || text[j + 1] === "$")) {
          found = j;
          break;
        }
        j++;
      }
      if (found > i + open) {
        if (buf) out.push({ t: "text", v: buf });
        buf = "";
        out.push({ t: display ? "dmath" : "math", v: text.slice(i + open, found) });
        i = found + open;
        continue;
      }
    }
    buf += ch;
    i++;
  }
  if (buf) out.push({ t: "text", v: buf });
  return out;
}

export function hasMath(text: string) {
  return text.includes("$");
}

/** Renders text with inline LaTeX. Cheap path when there is no math. */
export const MathText = memo(function MathText({ text, className }: { text: string; className?: string }) {
  const tokens = useMemo(() => (hasMath(text) ? tokenize(text) : null), [text]);
  if (!tokens) return <span className={className}>{text}</span>;
  return (
    <span className={className}>
      {tokens.map((tk, i) =>
        tk.t === "text" ? (
          <span key={i}>{tk.v}</span>
        ) : (
          <span key={i} dangerouslySetInnerHTML={{ __html: renderLatex(tk.v, false) }} />
        ),
      )}
    </span>
  );
});

export const MathBlock = memo(function MathBlock({ latex, className }: { latex: string; className?: string }) {
  const html = useMemo(() => renderLatex(latex, true), [latex]);
  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
});

/** Display-style formula for narrow cards: KaTeX only line-breaks (at relations/operators) in inline
 * mode, so render inline with \displaystyle instead of a non-wrapping display block. */
export const MathWrap = memo(function MathWrap({ latex, className }: { latex: string; className?: string }) {
  const html = useMemo(() => renderLatex(`\\displaystyle ${latex}`, false), [latex]);
  return <div className={className} dangerouslySetInnerHTML={{ __html: html }} />;
});

/** Strip LaTeX for plain contexts (document title, clipboard). */
export function plainText(text: string): string {
  return tokenize(text)
    .map((t) => (t.t === "text" ? t.v : t.v.replace(/\\[a-zA-Z]+/g, "").replace(/[{}^_]/g, "")))
    .join("");
}
