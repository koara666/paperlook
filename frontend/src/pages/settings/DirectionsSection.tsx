import { ChevronDown, Compass, Pencil, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { useAiConfig, useDirectionMutations, useDirections, useMeta } from "../../api/hooks";
import type { Direction } from "../../api/types";
import { ChipInput } from "../../components/ui/ChipInput";
import { Dialog, MenuItem, Popover, useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, EmptyState, Field, Input, Segmented, Skeleton, Switch } from "../../components/ui/primitives";
import { cn } from "../../lib/cn";

const WEIGHTS = [
  { value: 1, label: "低" },
  { value: 2, label: "较低" },
  { value: 3, label: "中" },
  { value: 4, label: "较高" },
  { value: 5, label: "高" },
];

type Draft = { id?: number; name: string; keywords: string[]; exclude: string[]; categories: string[]; weight: number; enabled: boolean };
const EMPTY: Draft = { name: "", keywords: [], exclude: [], categories: [], weight: 3, enabled: true };

function DirectionDialog({ open, initial, onClose }: { open: boolean; initial: Draft; onClose: () => void }) {
  const [d, setD] = useState<Draft>(initial);
  const [adv, setAdv] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const { data: meta } = useMeta();
  const { data: ai } = useAiConfig();
  const { create, update } = useDirectionMutations();
  const toast = useToast();
  useEffect(() => {
    if (open) {
      setD(initial);
      setAdv(initial.categories.length > 0 || initial.exclude.length > 0);
    }
  }, [open, initial]);

  const suggest = async () => {
    if (!d.name.trim()) return toast({ tone: "info", title: "请先填写方向名称" });
    setSuggesting(true);
    try {
      const r = await api.post<{ keywords: string[]; exclude: string[]; categories: string[] }>("/directions/suggest", { name: d.name });
      setD((x) => ({
        ...x,
        keywords: Array.from(new Set([...x.keywords, ...r.keywords])),
        exclude: x.exclude.length ? x.exclude : r.exclude,
        categories: x.categories.length ? x.categories : r.categories,
      }));
      if (r.categories.length) setAdv(true);
      toast({ tone: "success", title: `已添加 ${r.keywords.length} 个建议关键词`, description: "可以删除不需要的关键词" });
    } catch (e) {
      toast({ tone: "error", title: "生成失败", description: errorMessage(e) });
    } finally {
      setSuggesting(false);
    }
  };

  const save = () => {
    const body = { ...d, name: d.name.trim() };
    const opts = {
      onSuccess: () => {
        toast({ tone: "success", title: d.id ? "已保存修改" : "已添加研究方向" });
        onClose();
      },
      onError: (e: unknown) => toast({ tone: "error", title: "保存失败", description: errorMessage(e) }),
    };
    if (d.id) update.mutate({ ...body, id: d.id }, opts);
    else create.mutate(body, opts);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={d.id ? "编辑研究方向" : "添加研究方向"}
      description="用你自己的话描述方向，再添加几个论文中常见的英文关键词即可，无需任何搜索语法。"
      width="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            取消
          </Button>
          <Button variant="primary" onClick={save} disabled={!d.name.trim()} loading={create.isPending || update.isPending}>
            保存
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Field label="方向名称">
          <Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder="例如：多模态大模型、图神经网络、联邦学习" autoFocus />
        </Field>
        <Field
          label="关键词"
          extra={
            ai?.configured ? (
              <Button size="xs" variant="soft" icon={<Wand2 className="size-3.5" />} loading={suggesting} onClick={suggest}>
                AI 推荐关键词
              </Button>
            ) : undefined
          }
          hint="论文标题或摘要包含任一关键词即会被检索；标题命中权重更高。全大写的缩写（如 RAG、VLM）会区分大小写匹配。按回车添加。"
        >
          <ChipInput value={d.keywords} onChange={(v) => setD({ ...d, keywords: v })} placeholder="例如：vision-language model, RAG, contrastive learning" />
        </Field>
        <Field label="关注程度" hint="关注程度越高，这个方向在每日推荐中占的篇数越多。">
          <Segmented size="sm" value={d.weight} onChange={(v) => setD({ ...d, weight: v })} options={WEIGHTS} />
        </Field>
        <button onClick={() => setAdv(!adv)} className="flex items-center gap-1 text-xs text-text-3 hover:text-text">
          <ChevronDown className={cn("size-3.5 transition-transform", adv && "rotate-180")} /> 排除关键词与学科分类（可选）
        </button>
        {adv && (
          <div className="space-y-5">
            <Field label="排除关键词" hint="标题或摘要包含这些词的论文不会被推荐到这个方向。">
              <ChipInput tone="danger" value={d.exclude} onChange={(v) => setD({ ...d, exclude: v })} placeholder="例如：medical, survey" />
            </Field>
            <Field label="arXiv 学科分类" hint="限定 arXiv 检索范围，可减少无关领域的结果。不选则不限分类。">
              <div className="flex flex-wrap gap-1.5">
                {meta?.arxiv_categories.map((c) => {
                  const on = d.categories.includes(c.id);
                  return (
                    <button
                      key={c.id}
                      onClick={() => setD({ ...d, categories: on ? d.categories.filter((x) => x !== c.id) : [...d.categories, c.id] })}
                      className={cn(
                        "rounded-lg border px-2 py-1 text-xs transition-colors",
                        on ? "border-accent bg-accent-soft text-accent-text" : "border-border text-text-2 hover:border-border-strong",
                      )}
                    >
                      {c.name} <span className="font-mono opacity-60">{c.id}</span>
                    </button>
                  );
                })}
              </div>
            </Field>
          </div>
        )}
      </div>
    </Dialog>
  );
}

export function DirectionsSection() {
  const { data, isLoading } = useDirections();
  const { data: meta } = useMeta();
  const { update, remove, addPresets } = useDirectionMutations();
  const confirm = useConfirm();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const [dialog, setDialog] = useState<Draft | null>(null);

  useEffect(() => {
    if (params.get("new") === "1") {
      setDialog(EMPTY);
      params.delete("new");
      setParams(params, { replace: true });
    }
  }, [params, setParams]);

  if (isLoading) return <Skeleton className="h-64 rounded-2xl" />;
  const existing = new Set((data ?? []).map((d) => d.name));
  const presetsLeft = (meta?.direction_presets ?? []).filter((p) => !existing.has(p.name));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setDialog(EMPTY)}>
          添加研究方向
        </Button>
        {presetsLeft.length > 0 && (
          <Popover
            className="w-[280px]"
            trigger={({ toggle }) => (
              <Button icon={<Sparkles className="size-4" />} onClick={toggle}>
                从预设添加
              </Button>
            )}
          >
            {(close) =>
              presetsLeft.map((p) => (
                <MenuItem
                  key={p.key}
                  hint={p.name_en}
                  onClick={() => {
                    close();
                    addPresets.mutate([p.key], { onSuccess: () => toast({ tone: "success", title: `已添加「${p.name}」` }) });
                  }}
                >
                  {p.name}
                </MenuItem>
              ))
            }
          </Popover>
        )}
      </div>

      {!data?.length ? (
        <Card>
          <EmptyState icon={<Compass className="size-6" />} title="还没有研究方向" description="添加你关注的研究方向，PaperLook 会据此每天挑选论文。" />
        </Card>
      ) : (
        data.map((d: Direction) => (
          <Card key={d.id} className={cn("p-4 transition-opacity sm:p-5", !d.enabled && "opacity-60")}>
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-[15px] font-semibold text-text">{d.name}</h3>
                  <Badge tone="neutral">关注度：{WEIGHTS[d.weight - 1]?.label}</Badge>
                  {!d.enabled && <Badge tone="outline">已停用</Badge>}
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {d.keywords.length ? (
                    d.keywords.map((k) => (
                      <span key={k} className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs text-accent-text">
                        {k}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-text-3">没有关键词（仅按学科分类检索 arXiv）</span>
                  )}
                </div>
                {(d.exclude.length > 0 || d.categories.length > 0) && (
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-3">
                    {d.exclude.length > 0 && <span>排除：{d.exclude.join("、")}</span>}
                    {d.categories.length > 0 && <span className="font-mono">arXiv：{d.categories.join(" ")}</span>}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Switch checked={d.enabled} onChange={(v) => update.mutate({ id: d.id, enabled: v })} label="启用" />
                <button className="ml-2 rounded-lg p-1.5 text-text-3 hover:bg-surface-3 hover:text-text" onClick={() => setDialog({ ...d })} aria-label="编辑">
                  <Pencil className="size-4" />
                </button>
                <button
                  className="rounded-lg p-1.5 text-text-3 hover:bg-danger-soft hover:text-danger"
                  aria-label="删除"
                  onClick={async () => {
                    if (await confirm({ title: `删除「${d.name}」？`, description: "已推荐过的论文和 AI 分析结果会保留。", confirmText: "删除", danger: true })) remove.mutate(d.id);
                  }}
                >
                  <Trash2 className="size-4" />
                </button>
              </div>
            </div>
          </Card>
        ))
      )}
      <DirectionDialog open={!!dialog} initial={dialog ?? EMPTY} onClose={() => setDialog(null)} />
    </div>
  );
}
