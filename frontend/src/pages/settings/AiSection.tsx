import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, ExternalLink, Eye, EyeOff, KeyRound, Loader2, ShieldCheck, Trash2, XCircle, Zap } from "lucide-react";
import { useState } from "react";
import { api, errorMessage } from "../../api/client";
import { useAiConfig, useUsage } from "../../api/hooks";
import type { AiConfig, TestResult } from "../../api/types";
import { useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, Field, Input, Notice, Skeleton, Switch } from "../../components/ui/primitives";
import { cn } from "../../lib/cn";
import { timeAgo, tokens } from "../../lib/format";

const MODEL_INFO: Record<string, { title: string; desc: string; tag?: string }> = {
  "deepseek-flash": { title: "DeepSeek Flash", desc: "速度快、成本低，适合全文翻译与日常分析", tag: "推荐" },
  "deepseek-v4-pro": { title: "DeepSeek V4 Pro", desc: "推理能力更强，价格约为 Flash 的 3-4 倍" },
};

function TestSteps({ r }: { r: TestResult | AiConfig["last_test"] }) {
  if (!r?.steps?.length) return null;
  return (
    <ul className="mt-3 space-y-1.5">
      {r.steps.map((s) => (
        <li key={s.name} className="flex items-start gap-2 text-[13px]">
          {s.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />}
          <span>
            <span className="font-medium text-text">{s.name}</span>
            <span className="text-text-2"> — {s.detail}</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

export function AiSection() {
  const { data: cfg, isLoading } = useAiConfig();
  const usage = useUsage();
  const qc = useQueryClient();
  const toast = useToast();
  const confirm = useConfirm();
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<TestResult | null>(null);
  const [adv, setAdv] = useState(false);
  const [baseUrl, setBaseUrl] = useState<string | null>(null);

  if (isLoading || !cfg) return <Skeleton className="h-72 rounded-2xl" />;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["ai-config"] });
    qc.invalidateQueries({ queryKey: ["usage"] });
  };

  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      const r = await api.post<TestResult>("/ai/test", {});
      setTest(r);
      toast(r.ok ? { tone: "success", title: "连接正常", description: "DeepSeek API 可以正常使用" } : { tone: "error", title: "连接测试未通过", description: r.error });
    } catch (e) {
      toast({ tone: "error", title: "测试失败", description: errorMessage(e) });
    } finally {
      setTesting(false);
      refresh();
    }
  };

  const save = async (andTest: boolean) => {
    setSaving(true);
    try {
      await api.put("/ai/key", { api_key: key.trim() });
      setKey("");
      setEditing(false);
      toast({ tone: "success", title: "API Key 已安全保存" });
      refresh();
      if (andTest) await runTest();
    } catch (e) {
      toast({ tone: "error", title: "保存失败", description: errorMessage(e) });
    } finally {
      setSaving(false);
    }
  };

  const patch = async (body: Record<string, unknown>) => {
    try {
      await api.patch("/ai/config", body);
      refresh();
      qc.invalidateQueries({ queryKey: ["settings"] });
    } catch (e) {
      toast({ tone: "error", title: "保存失败", description: errorMessage(e) });
    }
  };

  const last = test ?? cfg.last_test;
  const statusOk = cfg.configured && last?.ok;
  const statusBad = cfg.configured && last && !last.ok;

  return (
    <div className="space-y-6">
      {/* status */}
      <Card className={cn("p-5", statusOk && "border-success/30", statusBad && "border-danger/30")}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className={cn("flex size-11 items-center justify-center rounded-xl", statusOk ? "bg-success-soft text-success" : statusBad ? "bg-danger-soft text-danger" : cfg.configured ? "bg-accent-soft text-accent" : "bg-warning-soft text-warning")}>
              {statusOk ? <CheckCircle2 className="size-5" /> : statusBad ? <XCircle className="size-5" /> : <KeyRound className="size-5" />}
            </span>
            <div>
              <div className="font-semibold text-text">
                {!cfg.configured ? "尚未配置 DeepSeek API Key" : statusOk ? "DeepSeek 连接正常" : statusBad ? "DeepSeek 连接异常" : "已保存 API Key（尚未测试）"}
              </div>
              <div className="mt-0.5 text-[13px] text-text-2">
                {!cfg.configured
                  ? "论文推荐不需要 API Key；翻译与 AI 分析需要。"
                  : last?.at
                    ? `上次测试：${timeAgo(last.at)}${statusBad && last.error ? ` · ${last.error}` : ""}`
                    : "建议点击「测试连接」确认配置可用"}
              </div>
            </div>
          </div>
          {cfg.configured && (
            <Button icon={testing ? undefined : <Zap className="size-4" />} loading={testing} onClick={runTest}>
              测试连接
            </Button>
          )}
        </div>
        {test && <TestSteps r={test} />}
      </Card>

      {/* key */}
      <Card className="p-5">
        <Field
          label="API Key"
          hint={
            <>
              在 DeepSeek 开放平台创建：
              <a href="https://platform.deepseek.com/api_keys" target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-accent-text hover:underline">
                platform.deepseek.com/api_keys <ExternalLink className="size-3" />
              </a>
              ，复制以 sk- 开头的 Key 粘贴到这里。
            </>
          }
        >
          {cfg.configured && !editing ? (
            <div className="flex flex-wrap items-center gap-2">
              <div className="flex h-9 flex-1 items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 font-mono text-sm text-text-2">
                <KeyRound className="size-3.5 text-text-3" />
                {cfg.key_masked}
              </div>
              <Button onClick={() => setEditing(true)}>更换</Button>
              <Button
                variant="ghost"
                icon={<Trash2 className="size-4" />}
                onClick={async () => {
                  if (await confirm({ title: "删除 API Key？", description: "删除后 AI 功能将不可用，已生成的翻译和分析结果不受影响。", confirmText: "删除", danger: true })) {
                    await api.del("/ai/key");
                    setTest(null);
                    refresh();
                    toast({ tone: "success", title: "已删除 API Key" });
                  }
                }}
              >
                删除
              </Button>
            </div>
          ) : (
            <form
              className="flex flex-wrap gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (key.trim()) save(true);
              }}
            >
              <div className="relative min-w-[240px] flex-1">
                <Input
                  type={show ? "text" : "password"}
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder="sk-..."
                  autoComplete="off"
                  spellCheck={false}
                  className="pr-9 font-mono"
                />
                <button type="button" onClick={() => setShow(!show)} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-3 hover:text-text" aria-label={show ? "隐藏" : "显示"}>
                  {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              <Button type="submit" variant="primary" loading={saving} disabled={!key.trim()}>
                保存并测试
              </Button>
              {editing && (
                <Button type="button" variant="ghost" onClick={() => { setEditing(false); setKey(""); }}>
                  取消
                </Button>
              )}
            </form>
          )}
        </Field>
        <div className="mt-4 flex items-start gap-2 rounded-lg bg-surface-2 px-3 py-2.5 text-xs leading-relaxed text-text-2">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" />
          <span>
            API Key 加密保存在本机的<strong className="font-medium text-text">{cfg.secret_backend}</strong>中，不会写入项目文件、不会出现在日志里，网页界面也只能看到打码后的形式。
          </span>
        </div>
      </Card>

      {/* model */}
      <Card className="p-5">
        <Field label="模型" hint="全文翻译固定使用非思考模式以保证速度；下面的「深度思考」只影响总结、模块与创新点分析。">
          <div className="grid gap-2 sm:grid-cols-2">
            {cfg.models.map((m) => {
              const info = MODEL_INFO[m] ?? { title: m, desc: "由 DeepSeek /models 接口返回的可用模型" };
              const on = cfg.model === m;
              return (
                <button
                  key={m}
                  onClick={() => patch({ model: m })}
                  className={cn("rounded-xl border p-3 text-left transition-all", on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-border hover:border-border-strong")}
                >
                  <div className="flex items-center gap-2">
                    <span className={cn("size-3.5 rounded-full border-[3px]", on ? "border-accent" : "border-border-strong")} />
                    <span className="text-sm font-medium text-text">{info.title}</span>
                    {info.tag && <Badge tone="accent">{info.tag}</Badge>}
                  </div>
                  <div className="mt-1 pl-5.5 text-xs text-text-3">{info.desc}</div>
                  <div className="mt-0.5 pl-5.5 font-mono text-[11px] text-text-3">{m}</div>
                </button>
              );
            })}
          </div>
        </Field>
        <div className="mt-5 flex items-start justify-between gap-4 border-t border-border pt-4">
          <div>
            <div className="text-[13px] font-medium text-text">分析时启用深度思考</div>
            <p className="mt-0.5 text-xs leading-relaxed text-text-3">让模型先推理再回答，分析更严谨，但耗时更长、消耗的 tokens 约为 2-5 倍。</p>
          </div>
          <Switch checked={cfg.thinking_for_analysis} onChange={(v) => patch({ thinking_for_analysis: v })} label="深度思考" />
        </div>
        <button onClick={() => setAdv(!adv)} className="mt-4 flex items-center gap-1 text-xs text-text-3 hover:text-text">
          <ChevronDown className={cn("size-3.5 transition-transform", adv && "rotate-180")} /> 高级设置
        </button>
        {adv && (
          <div className="mt-3">
            <Field label="服务地址" hint="一般无需修改。使用 DeepSeek 官方服务时保持 https://api.deepseek.com。">
              <div className="flex gap-2">
                <Input value={baseUrl ?? cfg.base_url} onChange={(e) => setBaseUrl(e.target.value)} className="font-mono" />
                <Button disabled={baseUrl === null || baseUrl === cfg.base_url} onClick={() => { patch({ base_url: baseUrl }); setBaseUrl(null); }}>
                  保存
                </Button>
                <Button variant="ghost" onClick={() => { patch({ base_url: "https://api.deepseek.com" }); setBaseUrl(null); }}>
                  恢复默认
                </Button>
              </div>
            </Field>
          </div>
        )}
      </Card>

      {/* usage */}
      <Card className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[13px] font-medium text-text">用量统计</div>
          <span className="text-xs text-text-3">仅统计 PaperLook 发出的请求</span>
        </div>
        {usage.data ? (
          <>
            <div className="grid grid-cols-3 gap-3">
              {[
                { l: "今天", v: usage.data.today },
                { l: "近 30 天", v: usage.data.last_30_days },
                { l: "累计", v: usage.data.total },
              ].map(({ l, v }) => (
                <div key={l} className="rounded-xl bg-surface-2 px-3 py-3">
                  <div className="text-xs text-text-3">{l}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums text-text">{tokens(v.prompt + v.completion)}</div>
                  <div className="text-[11px] text-text-3">tokens · {v.calls} 次调用</div>
                </div>
              ))}
            </div>
            {usage.data.by_kind_30d.length > 0 && (
              <div className="mt-4 space-y-1.5">
                {usage.data.by_kind_30d.map((k) => (
                  <div key={k.kind} className="flex items-center justify-between text-[13px]">
                    <span className="text-text-2">{KIND_LABEL[k.kind] ?? k.kind}</span>
                    <span className="tabular-nums text-text-3">
                      {k.calls} 次 · {tokens((k.prompt ?? 0) + (k.completion ?? 0))} tokens
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        ) : (
          <Loader2 className="size-4 animate-spin text-text-3" />
        )}
      </Card>
      {!cfg.configured && (
        <Notice tone="neutral">没有 API Key 时，论文检索、推荐、全文阅读等功能都可以正常使用。</Notice>
      )}
    </div>
  );
}

const KIND_LABEL: Record<string, string> = {
  translate: "全文翻译",
  glossary: "术语表",
  summary: "论文总结",
  modules: "关键模块",
  contributions: "创新点",
  abstract_translation: "摘要翻译",
  rerank: "AI 精排",
  suggest_keywords: "关键词建议",
  connection_test: "连接测试",
};
