import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, Copy, Download, ExternalLink, HardDrive, Info, KeyRound, RefreshCw, Trash2, Upload, XCircle } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { api, errorMessage } from "../../api/client";
import { useSettings, useSources, useStatus, useUpdateSettings } from "../../api/hooks";
import type { Settings, SourceInfo, UpdateInfo } from "../../api/types";
import { useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, Field, Input, Notice, Segmented, Skeleton, Switch } from "../../components/ui/primitives";
import { cn } from "../../lib/cn";
import { bytes, timeAgo } from "../../lib/format";

function Row({ title, desc, children, className }: { title: ReactNode; desc?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex items-start justify-between gap-4 py-4 first:pt-0 last:pb-0", className)}>
      <div className="min-w-0">
        <div className="text-[14px] font-medium text-text">{title}</div>
        {desc && <div className="mt-0.5 text-[13px] leading-relaxed text-text-3">{desc}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}

function useS() {
  const { data } = useSettings();
  const m = useUpdateSettings();
  return { s: data, set: (p: Partial<Settings> | Record<string, unknown>) => m.mutate(p) };
}

// ======================= Recommendation =======================
const PRESET_INFO: Record<string, { label: string; desc: string }> = {
  balanced: { label: "均衡", desc: "相关度为主，兼顾质量与时效（默认）" },
  relevance: { label: "相关性优先", desc: "尽量只推荐与研究方向高度吻合的论文" },
  quality: { label: "质量优先", desc: "更看重顶会接收、社区关注度、引用等信号" },
  fresh: { label: "最新优先", desc: "更偏向刚刚发布的论文" },
};

function WeightBars({ w }: { w: { relevance: number; quality: number; freshness: number } }) {
  return (
    <div className="mt-2 flex h-1.5 overflow-hidden rounded-full">
      <span className="bg-accent" style={{ width: `${w.relevance * 100}%` }} />
      <span className="bg-[#e9a93a]" style={{ width: `${w.quality * 100}%` }} />
      <span className="bg-success" style={{ width: `${w.freshness * 100}%` }} />
    </div>
  );
}

export function RecommendSection() {
  const { s, set } = useS();
  const [custom, setCustom] = useState("");
  const [showAlgo, setShowAlgo] = useState(false);
  const [w, setW] = useState<Settings["weights"] | null>(null);
  if (!s) return <Skeleton className="h-96 rounded-2xl" />;
  const weights = w ?? s.weights;
  const presets: Record<string, Settings["weights"]> = {
    balanced: { relevance: 0.55, quality: 0.25, freshness: 0.2 },
    relevance: { relevance: 0.7, quality: 0.15, freshness: 0.15 },
    quality: { relevance: 0.45, quality: 0.4, freshness: 0.15 },
    fresh: { relevance: 0.45, quality: 0.15, freshness: 0.4 },
  };
  const halfLife = { latest: 3, balanced: 7, relaxed: 21 }[s.time_preference];
  const f = (age: number) => Math.round((0.2 + 0.8 * Math.pow(0.5, age / halfLife)) * 100);

  return (
    <div className="space-y-6">
      <Card className="divide-y divide-border p-5">
        <Row title="每次推荐数量" desc="每次点击「获取今日推荐」挑选的论文篇数。">
          <div className="flex items-center gap-1 rounded-lg border border-border p-0.5">
            <button className="size-8 rounded-md text-text-2 hover:bg-surface-3" onClick={() => set({ daily_count: Math.max(1, s.daily_count - 1) })}>
              −
            </button>
            <span className="w-9 text-center text-sm font-semibold tabular-nums">{s.daily_count}</span>
            <button className="size-8 rounded-md text-text-2 hover:bg-surface-3" onClick={() => set({ daily_count: Math.min(50, s.daily_count + 1) })}>
              +
            </button>
          </div>
        </Row>
        <div className="py-4">
          <div className="text-[14px] font-medium text-text">发布时间范围</div>
          <div className="mt-0.5 text-[13px] text-text-3">只有在这个范围内首次发布的论文才会进入候选（arXiv 以 v1 提交日期为准）。</div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {[1, 3, 7, 14, 30].map((d) => (
              <button
                key={d}
                onClick={() => set({ window_days: d })}
                className={cn("h-8 rounded-lg px-3 text-[13px] font-medium", s.window_days === d ? "bg-accent text-white" : "bg-surface-3 text-text-2 hover:text-text")}
              >
                最近 {d} 天
              </button>
            ))}
            <form
              className="flex items-center gap-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                const n = parseInt(custom, 10);
                if (n >= 1 && n <= 365) {
                  set({ window_days: n });
                  setCustom("");
                }
              }}
            >
              <Input value={custom} onChange={(e) => setCustom(e.target.value.replace(/\D/g, ""))} placeholder={![1, 3, 7, 14, 30].includes(s.window_days) ? `当前 ${s.window_days} 天` : "自定义 N 天"} className="h-8 w-32" />
              <Button size="sm" type="submit" disabled={!custom}>
                确定
              </Button>
            </form>
          </div>
        </div>
        <div className="pt-4">
          <div className="text-[14px] font-medium text-text">时间偏好</div>
          <div className="mt-0.5 text-[13px] text-text-3">在时间范围内，越新的论文排序越靠前的程度。较早的论文仍可被推荐，不会被完全忽略。</div>
          <Segmented
            className="mt-3"
            value={s.time_preference}
            onChange={(v) => set({ time_preference: v })}
            options={[
              { value: "latest", label: "偏好最新" },
              { value: "balanced", label: "均衡" },
              { value: "relaxed", label: "不太在意" },
            ]}
          />
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-3">
            <span>时效分：今天 {f(0)}</span>
            <span>3 天前 {f(3)}</span>
            <span>7 天前 {f(7)}</span>
            <span>14 天前 {f(14)}</span>
            <span>30 天前 {f(30)}</span>
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <div className="text-[14px] font-medium text-text">排序策略</div>
        <div className="mt-0.5 text-[13px] text-text-3">决定研究相关度、论文质量、时效性三者在综合评分中的比重。</div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {Object.entries(PRESET_INFO).map(([k, info]) => {
            const on = s.ranking_preset === k;
            return (
              <button
                key={k}
                onClick={() => {
                  setW(null);
                  set({ ranking_preset: k as Settings["ranking_preset"] });
                }}
                className={cn("rounded-xl border p-3 text-left transition-all", on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-border hover:border-border-strong")}
              >
                <div className="text-sm font-medium text-text">{info.label}</div>
                <div className="mt-0.5 text-xs text-text-3">{info.desc}</div>
                <WeightBars w={presets[k]} />
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-text-3">
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-accent" />相关度</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[#e9a93a]" />质量</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-success" />时效</span>
        </div>
        <details className="group mt-4 rounded-xl border border-border" open={s.ranking_preset === "custom"}>
          <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2.5 text-[13px] font-medium text-text">
            自定义权重{s.ranking_preset === "custom" && <Badge tone="accent" className="ml-2">使用中</Badge>}
            <ChevronDown className="size-4 text-text-3 transition-transform group-open:rotate-180" />
          </summary>
          <div className="space-y-4 border-t border-border px-3 py-4">
            {(["relevance", "quality", "freshness"] as const).map((k) => (
              <div key={k}>
                <div className="mb-1 flex justify-between text-[13px]">
                  <span className="text-text-2">{{ relevance: "研究相关度", quality: "论文质量", freshness: "时效性" }[k]}</span>
                  <span className="tabular-nums text-text">{Math.round(weights[k] * 100)}%</span>
                </div>
                <input
                  type="range"
                  min={k === "relevance" ? 20 : 0}
                  max={100}
                  value={Math.round(weights[k] * 100)}
                  onChange={(e) => setW({ ...weights, [k]: Number(e.target.value) / 100 })}
                  className="w-full accent-[var(--accent)]"
                />
              </div>
            ))}
            <div className="flex items-center justify-between">
              <span className="text-xs text-text-3">保存时会自动归一化为 100%。相关度至少 20%，防止推荐与方向无关的论文。</span>
              <Button size="sm" variant="primary" disabled={!w} onClick={() => { set({ weights: weights }); setW(null); }}>
                应用
              </Button>
            </div>
          </div>
        </details>
      </Card>

      <Card className="divide-y divide-border p-5">
        <Row
          title={<span className="flex items-center gap-2">AI 精排 <Badge tone="warning">消耗 API</Badge></span>}
          desc="开启后，每次获取推荐时会把候选论文交给 AI（DeepSeek 或 Gemini）重新评估相关度，并生成中文标题与一句话概述。每次约 1-2 万 tokens（DeepSeek Flash 约几分钱；Gemini 免费档计 1 次请求）。打开应用时的自动获取不会使用 AI 精排。"
        >
          <Switch checked={s.ai_rerank} onChange={(v) => set({ ai_rerank: v })} label="AI 精排" />
        </Row>
        <Row title="打开应用时自动获取" desc="每天第一次打开「今日推荐」时，如果还没有推荐，就自动检索一次（只使用免费的论文数据接口，不调用 AI）。">
          <Switch checked={s.auto_fetch_on_open} onChange={(v) => set({ auto_fetch_on_open: v })} label="自动获取" />
        </Row>
      </Card>

      <Card className="p-5">
        <button onClick={() => setShowAlgo(!showAlgo)} className="flex w-full items-center justify-between text-left">
          <span className="flex items-center gap-2 text-[14px] font-medium text-text">
            <Info className="size-4 text-text-3" /> 推荐算法是怎样工作的？
          </span>
          <ChevronDown className={cn("size-4 text-text-3 transition-transform", showAlgo && "rotate-180")} />
        </button>
        {showAlgo && (
          <div className="mt-4 space-y-3 text-[13px] leading-relaxed text-text-2">
            <p>
              <strong className="text-text">1. 候选集合：</strong>从启用的来源检索每个研究方向的论文，按 arXiv ID / DOI / 标题去重，只保留时间范围内首次发布、且从未推荐过的论文。
            </p>
            <p>
              <strong className="text-text">2. 研究相关度：</strong>关键词出现在标题得满分、仅出现在摘要得部分分（出现越多越高），多个关键词命中会累加但有上限；arXiv 分类吻合有少量加分。相关度过低的论文直接排除——质量和时效再高也不会被推荐。
            </p>
            <p>
              <strong className="text-text">3. 论文质量：</strong>只使用可验证的信号——作者注明的顶会/期刊接收（如 "Accepted to CVPR 2026"）、期刊/会议的统计影响力（OpenAlex）、发表 30 天以上论文的引用数、Hugging Face 社区点赞、是否开源代码。缺少信号时按中性值处理，绝不凭空评级。
            </p>
            <p>
              <strong className="text-text">4. 时效性：</strong>半衰期衰减，最新的论文得分最高，但始终保留 20% 的底分。
            </p>
            <p>
              <strong className="text-text">5. 挑选：</strong>综合评分 = 各分项 × 权重。每个研究方向按「关注程度」分配名额，名额用不完时由其他方向的高分论文补上。
            </p>
          </div>
        )}
      </Card>
    </div>
  );
}

// ======================= Sources =======================
function SourceCard({ src }: { src: SourceInfo }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [key, setKey] = useState("");
  const [open, setOpen] = useState(false);
  const patch = async (body: Record<string, unknown>, msg?: string) => {
    try {
      const r = await api.patch(`/sources/${src.id}`, body);
      qc.setQueryData(["sources"], r);
      qc.invalidateQueries({ queryKey: ["settings"] });
      if (msg) toast({ tone: "success", title: msg });
    } catch (e) {
      toast({ tone: "error", title: "保存失败", description: errorMessage(e) });
    }
  };
  const last = src.last;
  return (
    <Card className={cn("p-5", !src.enabled && "bg-surface-2")}>
      <div className="flex items-start gap-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-[15px] font-semibold text-text">{src.name}</h3>
            <span className="text-xs text-text-3">{src.coverage}</span>
            {src.key_policy === "none" && <Badge tone="success">无需 Key</Badge>}
            {src.key_policy === "optional" && <Badge tone="neutral">Key 可选</Badge>}
            {src.key_policy === "recommended" && <Badge tone="warning">建议填写 Key</Badge>}
          </div>
          <p className="mt-1 text-[13px] leading-relaxed text-text-2">{src.description}</p>
          {src.enabled && last && (
            <div className="mt-2 flex items-center gap-1.5 text-xs">
              {last.errors?.length ? (
                <>
                  <XCircle className="size-3.5 text-danger" />
                  <span className="text-danger">{last.errors[0]}</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="size-3.5 text-success" />
                  <span className="text-text-3">
                    {timeAgo(last.at)}获取到 {last.fetched} 篇
                  </span>
                </>
              )}
            </div>
          )}
          {src.key_policy !== "none" && (
            <div className="mt-3">
              <button onClick={() => setOpen(!open)} className="flex items-center gap-1 text-xs text-text-3 hover:text-text">
                <KeyRound className="size-3.5" />
                {src.key_configured ? `已配置 API Key（${src.key_masked}）` : "填写 API Key"}
                <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
              </button>
              {open && (
                <div className="mt-2 space-y-2">
                  <p className="text-xs leading-relaxed text-text-3">{src.key_help}</p>
                  <div className="flex flex-wrap gap-2">
                    <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder="粘贴 API Key" className="h-8 max-w-xs font-mono" autoComplete="off" />
                    <Button size="sm" variant="primary" disabled={!key.trim()} onClick={() => { patch({ api_key: key }, "已保存"); setKey(""); }}>
                      保存
                    </Button>
                    {src.key_configured && (
                      <Button size="sm" variant="ghost" onClick={() => patch({ remove_key: true }, "已删除")}>
                        删除
                      </Button>
                    )}
                    <a href={src.homepage} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />}>
                        官网
                      </Button>
                    </a>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <Switch checked={src.enabled} onChange={(v) => patch({ enabled: v })} label={`启用 ${src.name}`} />
      </div>
    </Card>
  );
}

export function SourcesSection() {
  const { data, isLoading } = useSources();
  const qc = useQueryClient();
  if (isLoading || !data) return <Skeleton className="h-96 rounded-2xl" />;
  return (
    <div className="space-y-4">
      <Notice tone="neutral" icon={<Info className="size-4" />}>
        PaperLook 只从下列经过筛选的学术数据库获取论文，不会爬取任意网站。同一篇论文出现在多个来源时会自动合并。
      </Notice>
      {data.sources.map((s) => (
        <SourceCard key={s.id} src={s} />
      ))}
      <div className="pt-2 text-[13px] font-medium text-text-2">排序信号</div>
      {data.signals.map((sig) => (
        <Card key={sig.id} className="p-5">
          <div className="flex items-start gap-4">
            <div className="flex-1">
              <h3 className="text-[15px] font-semibold text-text">{sig.name}</h3>
              <p className="mt-1 text-[13px] leading-relaxed text-text-2">{sig.description}</p>
            </div>
            <Switch
              checked={sig.enabled}
              onChange={async (v) => {
                const r = await api.patch(`/sources/${sig.id}`, { enabled: v });
                qc.setQueryData(["sources"], r);
              }}
              label={sig.name}
            />
          </div>
        </Card>
      ))}
    </div>
  );
}

// ======================= AI features =======================
export function FeaturesSection() {
  const { s, set } = useS();
  if (!s) return <Skeleton className="h-80 rounded-2xl" />;
  const feat = (k: keyof Settings["ai"]["features"], v: boolean) => set({ ai: { ...s.ai, features: { ...s.ai.features, [k]: v } } });
  return (
    <div className="space-y-6">
      <Notice tone="accent" icon={<Info className="size-4" />} title="开启 ≠ 自动运行">
        开启只代表在论文页面显示对应按钮。任何 AI 功能都只会在你点击按钮后运行，打开论文时不会自动调用 API。
      </Notice>
      <Card className="divide-y divide-border p-5">
        <Row title="全文翻译" desc="按章节逐段翻译全文，保留公式、图表与参考文献。">
          <Switch checked={s.ai.features.translate} onChange={(v) => feat("translate", v)} label="全文翻译" />
        </Row>
        <Row title="论文总结" desc="研究问题、方法、实验结果、局限性与阅读建议。">
          <Switch checked={s.ai.features.summary} onChange={(v) => feat("summary", v)} label="论文总结" />
        </Row>
        <Row title="关键模块分析" desc="识别架构与核心模块，以及模块之间的协作关系。">
          <Switch checked={s.ai.features.modules} onChange={(v) => feat("modules", v)} label="关键模块分析" />
        </Row>
        <Row title="创新点提取" desc="区分作者声明、内容归纳与 AI 推断的贡献。">
          <Switch checked={s.ai.features.contributions} onChange={(v) => feat("contributions", v)} label="创新点提取" />
        </Row>
      </Card>
      <Card className="divide-y divide-border p-5">
        <Row title="保留英文术语" desc="重要术语首次出现时在中文后用括号保留英文原词，例如：对比学习（contrastive learning）。">
          <Switch checked={s.ai.keep_english_terms} onChange={(v) => set({ ai: { ...s.ai, keep_english_terms: v } })} label="保留英文术语" />
        </Row>
        <Row title="翻译附录" desc="关闭后全文翻译将跳过附录部分，可节省 tokens。">
          <Switch checked={s.ai.translate_appendix} onChange={(v) => set({ ai: { ...s.ai, translate_appendix: v } })} label="翻译附录" />
        </Row>
        <Row title="翻译并发数" desc="同时发送的翻译请求数。越大越快；如遇到频率限制可调低。">
          <Segmented size="sm" value={s.ai.concurrency} onChange={(v) => set({ ai: { ...s.ai, concurrency: v } })}
            options={[1, 2, 4, 6, 8].map((n) => ({ value: n, label: String(n) }))} />
        </Row>
      </Card>
    </div>
  );
}

// ======================= Reading =======================
export function ReadingSection() {
  const { s, set } = useS();
  if (!s) return <Skeleton className="h-60 rounded-2xl" />;
  const r = s.reading;
  return (
    <Card className="divide-y divide-border p-5">
      <Row title="外观" desc="深色模式适合夜间阅读。">
        <Segmented value={r.theme} onChange={(v) => set({ reading: { ...r, theme: v } })}
          options={[{ value: "system", label: "跟随系统" }, { value: "light", label: "浅色" }, { value: "dark", label: "深色" }]} />
      </Row>
      <Row title="阅读字号" desc="全文阅读器中的正文字号。">
        <Segmented value={r.font_size} onChange={(v) => set({ reading: { ...r, font_size: v } })}
          options={[{ value: "sm", label: "小" }, { value: "md", label: "中" }, { value: "lg", label: "大" }]} />
      </Row>
      <Row title="默认显示方式" desc="打开全文时默认显示原文、中英对照还是译文。">
        <Segmented value={r.translation_view} onChange={(v) => set({ reading: { ...r, translation_view: v } })}
          options={[{ value: "en", label: "原文" }, { value: "bilingual", label: "对照" }, { value: "zh", label: "译文" }]} />
      </Row>
    </Card>
  );
}

// ======================= Data & system =======================
export function DataSection() {
  const { data: st, refetch } = useStatus();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const fileRef = useRef<HTMLInputElement>(null);
  const [importing, setImporting] = useState(false);

  const clear = async (target: string, title: string, description: string) => {
    if (!(await confirm({ title, description, confirmText: "确认清理", danger: true }))) return;
    try {
      await api.post("/data/clear", { target });
      toast({ tone: "success", title: "已清理" });
      refetch();
      qc.invalidateQueries();
    } catch (e) {
      toast({ tone: "error", title: "清理失败", description: errorMessage(e) });
    }
  };

  const onImport = async (file: File) => {
    setImporting(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      if (!(await confirm({ title: "导入备份？", description: `将合并备份「${file.name}」中的设置、论文、推荐记录与 AI 结果。同 ID 的记录会被备份中的版本覆盖。`, confirmText: "导入" }))) return;
      const r = await api.post<{ counts: Record<string, number> }>("/data/import", data);
      toast({ tone: "success", title: "导入完成", description: `论文 ${r.counts.papers ?? 0} 篇，AI 结果 ${r.counts.ai_results ?? 0} 条` });
      qc.invalidateQueries();
    } catch (e) {
      toast({ tone: "error", title: "导入失败", description: e instanceof SyntaxError ? "文件不是有效的 JSON" : errorMessage(e) });
    } finally {
      setImporting(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  return (
    <div className="space-y-6">
      <Card className="p-5">
        {st ? (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {[
                { l: "论文", v: st.counts.papers },
                { l: "推荐记录", v: st.counts.recommendations },
                { l: "AI 分析", v: st.counts.ai_results },
                { l: "已翻译段落", v: st.counts.translated_units },
              ].map((x) => (
                <div key={x.l} className="rounded-xl bg-surface-2 px-3 py-3">
                  <div className="text-xs text-text-3">{x.l}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums text-text">{x.v}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2 text-[13px] text-text-2">
              <HardDrive className="size-4 text-text-3" />
              数据目录：
              <code className="rounded bg-surface-3 px-1.5 py-0.5 font-mono text-xs">{st.data_dir}</code>
              <span className="text-text-3">（{bytes(st.db_size)}）</span>
              <button
                onClick={() => navigator.clipboard.writeText(st.data_dir).then(() => toast({ tone: "success", title: "已复制路径" }))}
                className="rounded p-1 text-text-3 hover:bg-surface-3 hover:text-text"
                aria-label="复制路径"
              >
                <Copy className="size-3.5" />
              </button>
            </div>
          </>
        ) : (
          <Skeleton className="h-24" />
        )}
      </Card>

      <Card className="divide-y divide-border p-5">
        <Row title="导出备份" desc="导出设置、研究方向、论文、推荐记录、翻译与 AI 分析结果（JSON）。不包含 API Key。">
          <a href="/api/data/export">
            <Button icon={<Download className="size-4" />}>导出</Button>
          </a>
        </Row>
        <Row title="导入备份" desc="从之前导出的备份文件恢复数据。">
          <>
            <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={(e) => e.target.files?.[0] && onImport(e.target.files[0])} />
            <Button icon={<Upload className="size-4" />} loading={importing} onClick={() => fileRef.current?.click()}>
              导入
            </Button>
          </>
        </Row>
      </Card>

      <Card className="divide-y divide-border p-5">
        <Row title="清除检索缓存" desc="清除最近的检索结果缓存，下次推荐会重新请求各来源。">
          <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => clear("search_cache", "清除检索缓存？", "不影响任何推荐记录或 AI 结果。")}>
            清除
          </Button>
        </Row>
        <Row title="清除全文缓存" desc="删除已下载解析的全文（已翻译的论文会保留）。需要时会重新获取。">
          <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => clear("fulltext_cache", "清除全文缓存？", "已翻译过的论文的全文会保留。")}>
            清除
          </Button>
        </Row>
        <Row title="清空推荐历史" desc="忘记所有推荐过的论文，之后它们可能会被再次推荐。收藏、阅读状态与 AI 结果保留。">
          <Button variant="danger" icon={<Trash2 className="size-4" />} onClick={() => clear("history", "清空推荐历史？", "今日推荐与历史列表将被清空，此操作无法撤销。收藏和 AI 结果会保留。")}>
            清空
          </Button>
        </Row>
        <Row title="重置用量统计" desc="清零 AI 调用的 tokens 统计。">
          <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => clear("usage", "重置用量统计？", "只清除统计数据。")}>
            重置
          </Button>
        </Row>
      </Card>

      {st && (
        <Card className="p-5">
          <Field label="关于">
            <div className="grid grid-cols-[100px_1fr] gap-y-1.5 text-[13px]">
              <span className="text-text-3">版本</span>
              <span className="text-text">
                PaperLook {st.version}
                <UpdateCheck />
              </span>
              <span className="text-text-3">Python</span>
              <span className="text-text">{st.python}</span>
              <span className="text-text-3">密钥存储</span>
              <span className="text-text">{st.secret_backend}</span>
              <span className="text-text-3">运行时长</span>
              <span className="text-text">{Math.floor(st.uptime_seconds / 60)} 分钟</span>
            </div>
          </Field>
        </Card>
      )}
    </div>
  );
}

function UpdateCheck() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [info, setInfo] = useState<UpdateInfo | null>(null);
  const check = async () => {
    setBusy(true);
    try {
      const r = await api.get<UpdateInfo>("/update");
      setInfo(r);
      if (!r.has_update) toast({ tone: "success", title: "已是最新版本", description: r.latest ? `最新发布版本为 ${r.latest}` : "GitHub 上还没有发布版本" });
    } catch (e) {
      toast({ tone: "error", title: "检查更新失败", description: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };
  if (info?.has_update)
    return (
      <a href={info.url} target="_blank" rel="noreferrer" className="ml-2 inline-flex items-center gap-1 text-accent-text hover:underline">
        有新版本 {info.latest}，前往下载 <ExternalLink className="size-3" />
      </a>
    );
  return (
    <button onClick={check} disabled={busy} className="ml-2 inline-flex items-center gap-1 text-xs text-text-3 hover:text-text disabled:opacity-60">
      <RefreshCw className={cn("size-3", busy && "animate-spin")} /> 检查更新
    </button>
  );
}
