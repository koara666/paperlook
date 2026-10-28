import { Check, Loader2, NotebookPen, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { usePaperState } from "../../api/hooks";
import { Card, SectionTitle, Textarea } from "../../components/ui/primitives";

type Status = "idle" | "pending" | "saved" | "error";

/** Personal reading note, saved automatically (debounced) and flushed when leaving the page. */
export function NoteCard({ paperId, note }: { paperId: string; note: string | null }) {
  const setState = usePaperState(paperId);
  const [text, setText] = useState(note ?? "");
  const [editing, setEditing] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const saved = useRef(note ?? "");
  const latest = useRef(text);
  latest.current = text;
  const area = useRef<HTMLTextAreaElement>(null);

  const save = useCallback(
    (value: string) =>
      setState.mutate(
        { note: value },
        {
          onSuccess: () => {
            saved.current = value;
            setStatus(latest.current === value ? "saved" : "pending");
          },
          onError: () => setStatus("error"),
        },
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [paperId],
  );

  useEffect(() => {
    if (text === saved.current) return;
    setStatus("pending");
    const t = setTimeout(() => save(text), 800);
    return () => clearTimeout(t);
  }, [text, save]);

  // Leaving the page (or closing the window) within the debounce delay must not lose the last words.
  useEffect(() => {
    const flush = () => {
      if (latest.current === saved.current) return;
      saved.current = latest.current;
      fetch(`/api/papers/${paperId}/state`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: latest.current }),
        keepalive: true,
      }).catch(() => undefined);
    };
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [paperId]);

  useLayoutEffect(() => {
    const el = area.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.max(el.scrollHeight + 2, 112)}px`;
  }, [text, editing]);

  const show = editing || text.trim() !== "";
  return (
    <Card className="p-5 sm:p-6">
      <SectionTitle
        icon={<NotebookPen className="size-4" />}
        title="我的笔记"
        extra={
          status === "pending" ? (
            <span className="inline-flex items-center gap-1 text-xs text-text-3">
              <Loader2 className="size-3 animate-spin" /> 保存中
            </span>
          ) : status === "saved" ? (
            <span className="inline-flex items-center gap-1 text-xs text-success">
              <Check className="size-3" /> 已保存
            </span>
          ) : status === "error" ? (
            <button className="inline-flex items-center gap-1 text-xs text-danger hover:underline" onClick={() => save(text)}>
              <TriangleAlert className="size-3" /> 保存失败，点击重试
            </button>
          ) : null
        }
      />
      {show ? (
        <>
          <Textarea
            ref={area}
            value={text}
            autoFocus={editing && !note}
            onChange={(e) => setText(e.target.value)}
            onBlur={() => setEditing(false)}
            placeholder="记录你的想法、疑问、可借鉴的方法或实验设置……"
            className="resize-none overflow-hidden text-[14.5px] leading-relaxed"
            maxLength={20000}
          />
          <p className="mt-2 text-xs text-text-3">自动保存在本机，可在论文库中按「有笔记」筛选或搜索笔记内容，导出 AI 分析时一并导出。</p>
        </>
      ) : (
        <button
          onClick={() => setEditing(true)}
          className="flex w-full items-center gap-2 rounded-xl border border-dashed border-border-strong px-4 py-3.5 text-left text-[14px] text-text-3 transition-colors hover:border-accent/50 hover:bg-accent-soft/40 hover:text-accent-text"
        >
          <NotebookPen className="size-4 shrink-0" />
          添加笔记：记录你的想法、疑问或可借鉴之处
        </button>
      )}
    </Card>
  );
}
