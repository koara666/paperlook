import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, ExternalLink, Eye, EyeOff, Gift, Globe, KeyRound, Loader2, ShieldCheck, Trash2, XCircle, Zap } from "lucide-react";
import { useState, type ReactNode } from "react";
import { api, errorMessage } from "../../api/client";
import { useAiConfig, useUsage } from "../../api/hooks";
import type { AiConfig, AiProvider, ProviderConfig, TestResult } from "../../api/types";
import { useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, Field, Input, Notice, Skeleton, Switch } from "../../components/ui/primitives";
import { cn } from "../../lib/cn";
import { timeAgo, tokens } from "../../lib/format";

const MODEL_INFO: Record<string, { title: string; desc: string; tag?: string }> = {
  "deepseek-flash": { title: "DeepSeek Flash", desc: "速度快、成本低，适合全文翻译与日常分析", tag: "推荐" },
  "deepseek-v4-pro": { title: "DeepSeek V4 Pro", desc: "推理能力更强，价格约为 Flash 的 3-4 倍" },
  "gemini-3.5-flash-lite": { title: "Gemini 3.5 Flash-Lite", desc: "速度快，免费额度最多，适合全文翻译", tag: "推荐" },
  "gemini-3.8-flash": { title: "Gemini 3.8 Flash", desc: "质量更好，但免费额度很少（约每天 20 次请求）" },
  "gemini-3.1-flash-lite": { title: "Gemini 3.1 Flash-Lite", desc: "上一代 Flash-Lite，免费额度较多" },
};

const PROVIDER_INFO: Record<AiProvider, { title: string; tag: string; tone: "accent" | "success"; desc: string; defaultUrl: string }> = {
  deepseek: {
    title: "DeepSeek",
    tag: "稳定 · 很便宜",
    tone: "accent",
    desc: "按量付费，一篇论文全文翻译加三项分析约 0.5 元；国内可直接访问，速度快。",
    defaultUrl: "https://api.deepseek.com",
  },
  gemini: {
    title: "Google Gemini",
    tag: "有免费额度",
    tone: "success",
    desc: "Google AI Studio 的免费 Key 每天有一定请求次数；中国大陆需要代理才能访问。",
    defaultUrl: "https://generativelanguage.googleapis.com",
  },
};

const KEY_HELP: Record<AiProvider, { url: string; text: string; placeholder: string }> = {
  deepseek: { url: "https://platform.deepseek.com/api_keys", text: "platform.deepseek.com/api_keys", placeholder: "sk-..." },
  gemini: { url: "https://aistudio.google.com/apikey", text: "aistudio.google.com/apikey", placeholder: "AIza..." },
};

function TestSteps({ r }: { r: TestResult | AiConfig["last_test"] }) {
  if (!r?.steps?.length) return null;
  return (
    <ul className="mt-3 space-y-1.5">
      {r.steps.map((s) => (
        <li key={s.name} className="flex items-start gap-2 text-[13px]">
          {s.ok ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : <XCircle className="mt-0.5 size-4 shrink-0 text-danger" />}
          <span className="min-w-0 break-words">
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
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<TestResult | null>(null);

  if (isLoading || !cfg) return <Skeleton className="h-72 rounded-2xl" />;

  const provider = cfg.provider;
  const p = cfg.providers[provider];

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["ai-config"] });
    qc.invalidateQueries({ queryKey: ["usage"] });
  };

  const patch = async (body: Record<string, unknown>) => {
    try {
      await api.patch("/ai/config", body);
      refresh();
      qc.invalidateQueries({ queryKey: ["settings"] });
      return true;
    } catch (e) {
      toast({ tone: "error", title: "保存失败", description: errorMessage(e) });
      return false;
    }
  };

  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      const r = await api.post<TestResult>("/ai/test", { provider });
      setTest(r);
      toast(r.ok ? { tone: "success", title: "连接正常", description: r.message } : { tone: "error", title: "连接测试未通过", description: r.error });
    } catch (e) {
      toast({ tone: "error", title: "测试失败", description: errorMessage(e) });
    } finally {
      setTesting(false);
      refresh();
    }
  };

  const last = test ?? p.last_test;
  const statusOk = p.configured && last?.ok;
  const statusBad = p.configured && last && !last.ok;

  return (
    <div className="space-y-6">
      {/* provider */}
      <Card className="p-5">
        <Field label="使用哪个 AI 服务" hint="两个服务的 Key 分别保存，可以随时切换；已生成的翻译和分析结果不受影响。">
          <div className="grid gap-2 sm:grid-cols-2">
            {(Object.keys(PROVIDER_INFO) as AiProvider[]).map((id) => {
              const info = PROVIDER_INFO[id];
              const on = provider === id;
              const conf = cfg.providers[id].configured;
              return (
                <button
                  key={id}
                  onClick={() => {
                    if (on) return;
                    setTest(null);
                    patch({ provider: id });
                  }}
                  className={cn("rounded-xl border p-3 text-left transition-all", on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-border hover:border-border-strong")}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={cn("size-3.5 rounded-full border-[3px]", on ? "border-accent" : "border-border-strong")} />
                    <span className="text-sm font-medium text-text">{info.title}</span>
                    <Badge tone={info.tone}>{info.tag}</Badge>
                    <span className={cn("ml-auto text-[11px]", conf ? "text-success" : "text-text-3")}>{conf ? "已填写 Key" : "未填写 Key"}</span>
                  </div>
                  <div className="mt-1 pl-5.5 text-xs leading-relaxed text-text-3">{info.desc}</div>
                </button>
              );
            })}
          </div>
        </Field>
      </Card>

      {/* status */}
      <Card className={cn("p-5", statusOk && "border-success/30", statusBad && "border-danger/30")}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span className={cn("flex size-11 shrink-0 items-center justify-center rounded-xl", statusOk ? "bg-success-soft text-success" : statusBad ? "bg-danger-soft text-danger" : p.configured ? "bg-accent-soft text-accent" : "bg-warning-soft text-warning")}>
              {statusOk ? <CheckCircle2 className="size-5" /> : statusBad ? <XCircle className="size-5" /> : <KeyRound className="size-5" />}
            </span>
            <div className="min-w-0">
              <div className="font-semibold text-text">
                {!p.configured ? `尚未配置 ${p.label} API Key` : statusOk ? `${p.label} 连接正常` : statusBad ? `${p.label} 连接异常` : "已保存 API Key（尚未测试）"}
              </div>
              <div className="mt-0.5 text-[13px] text-text-2">
                {!p.configured
                  ? "论文推荐不需要 API Key；翻译与 AI 分析需要。"
                  : last?.at
                    ? `上次测试：${timeAgo(last.at)}${statusBad && last.error ? ` · ${last.error}` : ""}`
                    : "建议点击「测试连接」确认配置可用"}
              </div>
            </div>
          </div>
          {p.configured && (
            <Button icon={testing ? undefined : <Zap className="size-4" />} loading={testing} onClick={runTest}>
              测试连接
            </Button>
          )}
        </div>
        {test && <TestSteps r={test} />}
      </Card>

      <KeyCard key={provider} provider={provider} p={p} secretBackend={cfg.secret_backend} onSaved={runTest} onChanged={() => { setTest(null); refresh(); }} />

      {provider === "gemini" && <GeminiCard p={p} patch={patch} />}

      {/* model */}
      <Card className="p-5">
        <ModelPicker key={provider} p={p} onPick={(m) => patch(provider === "gemini" ? { gemini_model: m } : { model: m })} />
        <div className="mt-5 flex items-start justify-between gap-4 border-t border-border pt-4">
          <div>
            <div className="text-[13px] font-medium text-text">分析时启用深度思考</div>
            <p className="mt-0.5 text-xs leading-relaxed text-text-3">
              让模型先推理再回答，分析更严谨，但耗时更长、消耗的 tokens 约为 2-5 倍。全文翻译始终使用最低思考强度以保证速度。
            </p>
          </div>
          <Switch checked={cfg.thinking_for_analysis} onChange={(v) => patch({ thinking_for_analysis: v })} label="深度思考" />
        </div>
        <AdvancedUrl key={provider} provider={provider} p={p} patch={patch} />
      </Card>

      {/* usage */}
      <Card className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[13px] font-medium text-text">用量统计</div>
          <span className="text-xs text-text-3">仅统计 PaperLook 发出的请求（两个服务合计）</span>
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
      {!p.configured && <Notice tone="neutral">没有 API Key 时，论文检索、推荐、全文阅读等功能都可以正常使用。</Notice>}
    </div>
  );
}

function KeyCard({ provider, p, secretBackend, onSaved, onChanged }: { provider: AiProvider; p: ProviderConfig; secretBackend: string; onSaved: () => void; onChanged: () => void }) {
  const toast = useToast();
  const confirm = useConfirm();
  const [key, setKey] = useState("");
  const [show, setShow] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const help = KEY_HELP[provider];

  const save = async () => {
    setSaving(true);
    try {
      await api.put("/ai/key", { api_key: key.trim(), provider });
      setKey("");
      setEditing(false);
      toast({ tone: "success", title: "API Key 已安全保存" });
      onChanged();
      onSaved();
    } catch (e) {
      toast({ tone: "error", title: "保存失败", description: errorMessage(e) });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="p-5">
      <Field
        label={`${p.label} API Key`}
        hint={
          <>
            {provider === "gemini" ? "用 Google 账号登录 AI Studio 免费创建：" : "在 DeepSeek 开放平台创建："}
            <a href={help.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-accent-text hover:underline">
              {help.text} <ExternalLink className="size-3" />
            </a>
            {provider === "gemini" ? "（网页同样需要代理），复制以 AIza 开头的 Key 粘贴到这里。" : "，复制以 sk- 开头的 Key 粘贴到这里。"}
          </>
        }
      >
        {p.configured && !editing ? (
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 font-mono text-sm text-text-2">
              <KeyRound className="size-3.5 shrink-0 text-text-3" />
              <span className="truncate">{p.key_masked}</span>
            </div>
            <Button onClick={() => setEditing(true)}>更换</Button>
            <Button
              variant="ghost"
              icon={<Trash2 className="size-4" />}
              onClick={async () => {
                if (await confirm({ title: `删除 ${p.label} API Key？`, description: "删除后 AI 功能将不可用，已生成的翻译和分析结果不受影响。", confirmText: "删除", danger: true })) {
                  await api.del(`/ai/key?provider=${provider}`);
                  onChanged();
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
              if (key.trim()) save();
            }}
          >
            <div className="relative min-w-[240px] flex-1">
              <Input
                type={show ? "text" : "password"}
                value={key}
                onChange={(e) => setKey(e.target.value)}
                placeholder={help.placeholder}
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
          API Key 加密保存在本机的<strong className="font-medium text-text">{secretBackend}</strong>中，不会写入项目文件、不会出现在日志里，网页界面也只能看到打码后的形式。
        </span>
      </div>
    </Card>
  );
}

function GeminiCard({ p, patch }: { p: ProviderConfig; patch: (b: Record<string, unknown>) => Promise<boolean> }) {
  const [proxy, setProxy] = useState<string | null>(null);
  const today = Object.entries(p.requests_today ?? {});
  const reset = p.reset_hour_beijing ?? 15;
  return (
    <Card className="p-5">
      <div className="flex items-center gap-2 text-[13px] font-medium text-text">
        <Gift className="size-4 text-success" /> 免费额度
      </div>
      <div className="mt-2 space-y-1.5 text-xs leading-relaxed text-text-2">
        <p>
          免费额度按<strong className="font-medium text-text">请求次数</strong>计算，每个模型分开计数，每天北京时间 {reset}:00（太平洋时间 0 点）重置。Google 不再公布固定数值，以你在
          <a href="https://aistudio.google.com/rate-limit" target="_blank" rel="noreferrer" className="mx-0.5 inline-flex items-center gap-0.5 text-accent-text hover:underline">
            AI Studio 额度页面 <ExternalLink className="size-3" />
          </a>
          看到的为准。2026 年 10 月的公开资料：Flash-Lite 约每分钟 10 次、每天 500 次；Flash 约每分钟 5 次、每天 20 次。
        </p>
        <p>
          PaperLook 的消耗（免费档模式）：全文翻译约每 1500 词 1 次请求（1.3 万词的论文约 10 次）；总结、关键模块、创新点、摘要翻译各 1 次。按上面的额度，Flash-Lite 每天可以完整处理二三十篇论文；Flash 每天只够翻译一两篇或分析几篇。
        </p>
        <p className="text-text-3">免费档的请求内容可能被 Google 用于改进产品；论文本身是公开的，一般无妨。</p>
      </div>
      <div className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-xs text-text-2">
        今日已用（自北京时间 {reset}:00 起）：
        {today.length ? today.map(([m, n]) => <span key={m} className="ml-1.5 font-mono tabular-nums text-text">{m} {n} 次</span>) : <span className="ml-1 text-text-3">还没有请求</span>}
      </div>

      <div className="mt-4 flex items-start justify-between gap-4 border-t border-border pt-4">
        <div>
          <div className="text-[13px] font-medium text-text">免费档模式</div>
          <p className="mt-0.5 text-xs leading-relaxed text-text-3">
            自动限速（当前模型每分钟最多 {p.rpm ?? 5} 次）、合并翻译请求以节省次数，避免触发「请求过于频繁」。如果已为项目开通付费，可以关闭以加快翻译。
          </p>
        </div>
        <Switch checked={!!p.free_tier} onChange={(v) => patch({ gemini_free_tier: v })} label="免费档模式" />
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Field
          label={
            <span className="inline-flex items-center gap-1.5">
              <Globe className="size-3.5 text-text-3" /> 代理地址（可选）
            </span>
          }
          hint="中国大陆无法直接访问 Gemini。留空时使用系统代理（代理软件开启「系统代理」即可）；也可以填写代理软件的本地端口，例如 Clash 为 http://127.0.0.1:7890，Clash Verge 为 http://127.0.0.1:7897。代理节点需在支持地区（美国、日本、新加坡、台湾等；香港不支持）。"
        >
          <div className="flex flex-wrap gap-2">
            <Input
              value={proxy ?? p.proxy ?? ""}
              onChange={(e) => setProxy(e.target.value)}
              placeholder="留空 = 使用系统代理"
              spellCheck={false}
              className="min-w-[220px] flex-1 font-mono"
            />
            <Button
              disabled={proxy === null || proxy.trim() === (p.proxy ?? "")}
              onClick={async () => {
                if (await patch({ gemini_proxy: proxy ?? "" })) setProxy(null);
              }}
            >
              保存
            </Button>
          </div>
        </Field>
      </div>
    </Card>
  );
}

function ModelPicker({ p, onPick }: { p: ProviderConfig; onPick: (m: string) => void }) {
  const [all, setAll] = useState(false);
  const known = p.models.filter((m) => MODEL_INFO[m] || m === p.model);
  const list = all || p.models.length <= 4 ? p.models : known;
  const hidden = p.models.length - list.length;
  const hint: ReactNode =
    p.label === "Gemini"
      ? "推荐 Flash-Lite：免费额度最多、速度快。点击「测试连接」可以刷新你的 Key 能用的全部模型。"
      : "全文翻译固定使用非思考模式以保证速度；下面的「深度思考」只影响总结、模块与创新点分析。";
  return (
    <Field label="模型" hint={hint}>
      <div className="grid gap-2 sm:grid-cols-2">
        {list.map((m) => {
          const info = MODEL_INFO[m] ?? { title: m, desc: `由 ${p.label} 接口返回的可用模型` };
          const on = p.model === m;
          return (
            <button
              key={m}
              onClick={() => onPick(m)}
              className={cn("min-w-0 rounded-xl border p-3 text-left transition-all", on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-border hover:border-border-strong")}
            >
              <div className="flex items-center gap-2">
                <span className={cn("size-3.5 shrink-0 rounded-full border-[3px]", on ? "border-accent" : "border-border-strong")} />
                <span className="truncate text-sm font-medium text-text">{info.title}</span>
                {info.tag && <Badge tone="accent">{info.tag}</Badge>}
              </div>
              <div className="mt-1 pl-5.5 text-xs text-text-3">{info.desc}</div>
              <div className="mt-0.5 truncate pl-5.5 font-mono text-[11px] text-text-3">{m}</div>
            </button>
          );
        })}
      </div>
      {(hidden > 0 || all) && p.models.length > 4 && (
        <button onClick={() => setAll(!all)} className="mt-2 flex items-center gap-1 text-xs text-text-3 hover:text-text">
          <ChevronDown className={cn("size-3.5 transition-transform", all && "rotate-180")} />
          {all ? "只显示推荐模型" : `显示全部 ${p.models.length} 个模型`}
        </button>
      )}
    </Field>
  );
}

function AdvancedUrl({ provider, p, patch }: { provider: AiProvider; p: ProviderConfig; patch: (b: Record<string, unknown>) => Promise<boolean> }) {
  const [adv, setAdv] = useState(false);
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const field = provider === "gemini" ? "gemini_base_url" : "base_url";
  const def = PROVIDER_INFO[provider].defaultUrl;
  return (
    <>
      <button onClick={() => setAdv(!adv)} className="mt-4 flex items-center gap-1 text-xs text-text-3 hover:text-text">
        <ChevronDown className={cn("size-3.5 transition-transform", adv && "rotate-180")} /> 高级设置
      </button>
      {adv && (
        <div className="mt-3">
          <Field
            label="服务地址"
            hint={provider === "gemini" ? `一般无需修改。使用 Google 官方服务时保持 ${def}；也可以填写你自己搭建的 Gemini API 中转地址。` : `一般无需修改。使用 DeepSeek 官方服务时保持 ${def}。`}
          >
            <div className="flex flex-wrap gap-2">
              <Input value={baseUrl ?? p.base_url} onChange={(e) => setBaseUrl(e.target.value)} className="min-w-[220px] flex-1 font-mono" />
              <Button
                disabled={baseUrl === null || baseUrl === p.base_url}
                onClick={async () => {
                  if (await patch({ [field]: baseUrl })) setBaseUrl(null);
                }}
              >
                保存
              </Button>
              <Button variant="ghost" onClick={() => { patch({ [field]: def }); setBaseUrl(null); }}>
                恢复默认
              </Button>
            </div>
          </Field>
        </div>
      )}
    </>
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
