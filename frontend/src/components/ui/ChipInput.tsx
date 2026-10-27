import { X } from "lucide-react";
import { useState, type KeyboardEvent } from "react";
import { cn } from "../../lib/cn";

/** Keyword editor: type and press Enter / comma to add; Backspace removes the last chip. */
export function ChipInput({
  value,
  onChange,
  placeholder,
  tone = "accent",
  max = 30,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  tone?: "accent" | "danger";
  max?: number;
}) {
  const [text, setText] = useState("");

  const add = (raw: string) => {
    const parts = raw
      .split(/[,，;；\n]/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!parts.length) return;
    const next = [...value];
    for (const p of parts) {
      if (!next.some((x) => x.toLowerCase() === p.toLowerCase()) && next.length < max) next.push(p);
    }
    onChange(next);
    setText("");
  };

  const onKey = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === "," || e.key === "，") {
      e.preventDefault();
      add(text);
    } else if (e.key === "Backspace" && !text && value.length) {
      onChange(value.slice(0, -1));
    }
  };

  return (
    <div className="flex min-h-[38px] w-full flex-wrap items-center gap-1.5 rounded-lg border border-border bg-surface px-2 py-1.5 focus-within:border-accent focus-within:ring-3 focus-within:ring-[var(--ring)]">
      {value.map((v) => (
        <span
          key={v}
          className={cn(
            "inline-flex h-6 items-center gap-1 rounded-md pl-2 pr-1 text-[13px]",
            tone === "danger" ? "bg-danger-soft text-danger" : "bg-accent-soft text-accent-text",
          )}
        >
          {v}
          <button
            type="button"
            onClick={() => onChange(value.filter((x) => x !== v))}
            className="rounded p-0.5 opacity-60 hover:opacity-100"
            aria-label={`删除 ${v}`}
          >
            <X className="size-3" />
          </button>
        </span>
      ))}
      <input
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKey}
        onBlur={() => text && add(text)}
        onPaste={(e) => {
          const t = e.clipboardData.getData("text");
          if (/[,，;\n]/.test(t)) {
            e.preventDefault();
            add(t);
          }
        }}
        placeholder={value.length ? "" : placeholder}
        className="h-6 min-w-[120px] flex-1 bg-transparent px-1 text-sm text-text placeholder:text-text-3 focus:outline-none"
      />
    </div>
  );
}
