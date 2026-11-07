import { useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, ExternalLink, Eye, EyeOff, Gift, Globe, KeyRound, Loader2, ShieldCheck, Trash2, XCircle, Zap } from "lucide-react";
import { useState, type ReactNode } from "react";
import { api, errorMessage } from "../../api/client";
import { useAiConfig, useUsage } from "../../api/hooks";
import type { AiConfig, AiProvider, ProviderConfig, TestResult } from "../../api/types";
import { useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, Field, Input, Notice, Skeleton, Switch } from "../../components/ui/primitives";
import { rich, t, type MsgKey } from "../../i18n";
import { cn } from "../../lib/cn";
import { timeAgo, tokens } from "../../lib/format";

const MODEL_INFO: Record<string, { title: string; desc: MsgKey; recommended?: boolean }> = {
  "deepseek-flash": { title: "DeepSeek Flash", desc: "model.deepseek_flash", recommended: true },
  "deepseek-v4-pro": { title: "DeepSeek V4 Pro", desc: "model.deepseek_pro" },
  "gemini-3.5-flash-lite": { title: "Gemini 3.5 Flash-Lite", desc: "model.gemini_lite", recommended: true },
  "gemini-3.8-flash": { title: "Gemini 3.8 Flash", desc: "model.gemini_flash" },
  "gemini-3.1-flash-lite": { title: "Gemini 3.1 Flash-Lite", desc: "model.gemini_old_lite" },
};

const PROVIDER_INFO: Record<AiProvider, { title: string; tag: MsgKey; tone: "accent" | "success"; desc: MsgKey; defaultUrl: string }> = {
  deepseek: {
    title: "DeepSeek",
    tag: "aiset.ds_tag",
    tone: "accent",
    desc: "aiset.ds_desc",
    defaultUrl: "https://api.deepseek.com",
  },
  gemini: {
    title: "Google Gemini",
    tag: "aiset.gm_tag",
    tone: "success",
    desc: "aiset.gm_desc",
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
      toast({ tone: "error", title: t("common.save_failed"), description: errorMessage(e) });
      return false;
    }
  };

  const runTest = async () => {
    setTesting(true);
    setTest(null);
    try {
      const r = await api.post<TestResult>("/ai/test", { provider });
      setTest(r);
      toast(r.ok ? { tone: "success", title: t("aiset.test_ok"), description: r.message } : { tone: "error", title: t("aiset.test_bad"), description: r.error });
    } catch (e) {
      toast({ tone: "error", title: t("aiset.test_failed"), description: errorMessage(e) });
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
        <Field label={t("aiset.which")} hint={t("aiset.which_hint")}>
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
                    <Badge tone={info.tone}>{t(info.tag)}</Badge>
                    <span className={cn("ml-auto text-[11px]", conf ? "text-success" : "text-text-3")}>{conf ? t("aiset.has_key") : t("aiset.no_key")}</span>
                  </div>
                  <div className="mt-1 pl-5.5 text-xs leading-relaxed text-text-3">{t(info.desc)}</div>
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
                {!p.configured ? t("aiset.st_none", { provider: p.label }) : statusOk ? t("aiset.st_ok", { provider: p.label }) : statusBad ? t("aiset.st_bad", { provider: p.label }) : t("aiset.st_untested")}
              </div>
              <div className="mt-0.5 text-[13px] text-text-2">
                {!p.configured
                  ? t("aiset.st_none_desc")
                  : last?.at
                    ? t("aiset.last_test", { when: timeAgo(last.at) }) + (statusBad && last.error ? ` · ${last.error}` : "")
                    : t("aiset.suggest_test")}
              </div>
            </div>
          </div>
          {p.configured && (
            <Button icon={testing ? undefined : <Zap className="size-4" />} loading={testing} onClick={runTest}>
              {t("aiset.test")}
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
            <div className="text-[13px] font-medium text-text">{t("aiset.thinking")}</div>
            <p className="mt-0.5 text-xs leading-relaxed text-text-3">
              {t("aiset.thinking_desc")}
            </p>
          </div>
          <Switch checked={cfg.thinking_for_analysis} onChange={(v) => patch({ thinking_for_analysis: v })} label={t("ai.thinking")} />
        </div>
        <AdvancedUrl key={provider} provider={provider} p={p} patch={patch} />
      </Card>

      {/* usage */}
      <Card className="p-5">
        <div className="mb-3 flex items-center justify-between">
          <div className="text-[13px] font-medium text-text">{t("aiset.usage")}</div>
          <span className="text-xs text-text-3">{t("aiset.usage_note")}</span>
        </div>
        {usage.data ? (
          <>
            <div className="grid grid-cols-3 gap-3">
              {[
                { l: t("aiset.today"), v: usage.data.today },
                { l: t("aiset.last30"), v: usage.data.last_30_days },
                { l: t("aiset.total"), v: usage.data.total },
              ].map(({ l, v }) => (
                <div key={l} className="rounded-xl bg-surface-2 px-3 py-3">
                  <div className="text-xs text-text-3">{l}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums text-text">{tokens(v.prompt + v.completion)}</div>
                  <div className="text-[11px] text-text-3">{t("aiset.calls", { n: v.calls })}</div>
                </div>
              ))}
            </div>
            {usage.data.by_kind_30d.length > 0 && (
              <div className="mt-4 space-y-1.5">
                {usage.data.by_kind_30d.map((k) => (
                  <div key={k.kind} className="flex items-center justify-between text-[13px]">
                    <span className="text-text-2">{KIND_LABEL[k.kind] ? t(KIND_LABEL[k.kind]) : k.kind}</span>
                    <span className="tabular-nums text-text-3">
                      {t("aiset.kind_usage", { n: k.calls, tokens: tokens((k.prompt ?? 0) + (k.completion ?? 0)) })}
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
      {!p.configured && <Notice tone="neutral">{t("aiset.no_key_ok")}</Notice>}
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
      toast({ tone: "success", title: t("aiset.key_saved") });
      onChanged();
      onSaved();
    } catch (e) {
      toast({ tone: "error", title: t("common.save_failed"), description: errorMessage(e) });
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
            {provider === "gemini" ? t("aiset.key_where_gm") : t("aiset.key_where_ds")}
            <a href={help.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-0.5 text-accent-text hover:underline">
              {help.text} <ExternalLink className="size-3" />
            </a>
            {provider === "gemini" ? t("aiset.key_paste_gm") : t("aiset.key_paste_ds")}
          </>
        }
      >
        {p.configured && !editing ? (
          <div className="flex flex-wrap items-center gap-2">
            <div className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg border border-border bg-surface-2 px-3 font-mono text-sm text-text-2">
              <KeyRound className="size-3.5 shrink-0 text-text-3" />
              <span className="truncate">{p.key_masked}</span>
            </div>
            <Button onClick={() => setEditing(true)}>{t("aiset.replace")}</Button>
            <Button
              variant="ghost"
              icon={<Trash2 className="size-4" />}
              onClick={async () => {
                if (await confirm({ title: t("aiset.delete_q", { provider: p.label }), description: t("aiset.delete_desc"), confirmText: t("common.delete"), danger: true })) {
                  await api.del(`/ai/key?provider=${provider}`);
                  onChanged();
                  toast({ tone: "success", title: t("aiset.key_deleted") });
                }
              }}
            >
              {t("common.delete")}
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
              <button type="button" onClick={() => setShow(!show)} className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-text-3 hover:text-text" aria-label={show ? t("aiset.hide") : t("aiset.show")}>
                {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            <Button type="submit" variant="primary" loading={saving} disabled={!key.trim()}>
              {t("aiset.save_test")}
            </Button>
            {editing && (
              <Button type="button" variant="ghost" onClick={() => { setEditing(false); setKey(""); }}>
                {t("common.cancel")}
              </Button>
            )}
          </form>
        )}
      </Field>
      <div className="mt-4 flex items-start gap-2 rounded-lg bg-surface-2 px-3 py-2.5 text-xs leading-relaxed text-text-2">
        <ShieldCheck className="mt-0.5 size-4 shrink-0 text-success" />
        <span>
          {rich("aiset.key_safety", { backend: secretBackend }, { b: (x) => <strong className="font-medium text-text">{x}</strong> })}
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
        <Gift className="size-4 text-success" /> {t("gm.free")}
      </div>
      <div className="mt-2 space-y-1.5 text-xs leading-relaxed text-text-2">
        <p>
          {rich("gm.free_desc", { hour: reset, hour_next: (reset + 1) % 24 }, {
            b: (x) => <strong className="font-medium text-text">{x}</strong>,
            a: (x) => (
              <a href="https://aistudio.google.com/rate-limit" target="_blank" rel="noreferrer" className="mx-0.5 inline-flex items-center gap-0.5 text-accent-text hover:underline">
                {x} <ExternalLink className="size-3" />
              </a>
            ),
          })}
        </p>
        <p>
          {t("gm.consumption")}
        </p>
        <p className="text-text-3">{t("gm.privacy")}</p>
      </div>
      <div className="mt-3 rounded-lg bg-surface-2 px-3 py-2 text-xs text-text-2">
        {t("gm.used_today", { hour: reset, hour_next: (reset + 1) % 24 })}
        {today.length ? today.map(([m, n]) => <span key={m} className="ml-1.5 font-mono tabular-nums text-text">{t("gm.model_count", { model: m, n })}</span>) : <span className="ml-1 text-text-3">{t("gm.no_requests")}</span>}
      </div>

      <div className="mt-4 flex items-start justify-between gap-4 border-t border-border pt-4">
        <div>
          <div className="text-[13px] font-medium text-text">{t("gm.free_mode")}</div>
          <p className="mt-0.5 text-xs leading-relaxed text-text-3">
            {t("gm.free_mode_desc", { rpm: p.rpm ?? 5 })}
          </p>
        </div>
        <Switch checked={!!p.free_tier} onChange={(v) => patch({ gemini_free_tier: v })} label={t("gm.free_mode")} />
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <Field
          label={
            <span className="inline-flex items-center gap-1.5">
              <Globe className="size-3.5 text-text-3" /> {t("gm.proxy")}
            </span>
          }
          hint={t("gm.proxy_hint")}
        >
          <div className="flex flex-wrap gap-2">
            <Input
              value={proxy ?? p.proxy ?? ""}
              onChange={(e) => setProxy(e.target.value)}
              placeholder={t("gm.proxy_placeholder")}
              spellCheck={false}
              className="min-w-[220px] flex-1 font-mono"
            />
            <Button
              disabled={proxy === null || proxy.trim() === (p.proxy ?? "")}
              onClick={async () => {
                if (await patch({ gemini_proxy: proxy ?? "" })) setProxy(null);
              }}
            >
              {t("common.save")}
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
      ? t("model.hint_gemini")
      : t("model.hint_deepseek");
  return (
    <Field label={t("model.label")} hint={hint}>
      <div className="grid gap-2 sm:grid-cols-2">
        {list.map((m) => {
          const known = MODEL_INFO[m];
          const info = { title: known?.title ?? m, desc: known ? t(known.desc) : t("model.from_api", { provider: p.label }), recommended: known?.recommended };
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
                {info.recommended && <Badge tone="accent">{t("model.recommended")}</Badge>}
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
          {all ? t("model.show_recommended") : t("model.show_all", { n: p.models.length })}
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
        <ChevronDown className={cn("size-3.5 transition-transform", adv && "rotate-180")} /> {t("aiset.advanced")}
      </button>
      {adv && (
        <div className="mt-3">
          <Field
            label={t("aiset.base_url")}
            hint={provider === "gemini" ? t("aiset.base_url_gm", { url: def }) : t("aiset.base_url_ds", { url: def })}
          >
            <div className="flex flex-wrap gap-2">
              <Input value={baseUrl ?? p.base_url} onChange={(e) => setBaseUrl(e.target.value)} className="min-w-[220px] flex-1 font-mono" />
              <Button
                disabled={baseUrl === null || baseUrl === p.base_url}
                onClick={async () => {
                  if (await patch({ [field]: baseUrl })) setBaseUrl(null);
                }}
              >
                {t("common.save")}
              </Button>
              <Button variant="ghost" onClick={() => { patch({ [field]: def }); setBaseUrl(null); }}>
                {t("aiset.restore_default")}
              </Button>
            </div>
          </Field>
        </div>
      )}
    </>
  );
}

const KIND_LABEL: Record<string, MsgKey> = {
  translate: "ov.tile.translate",
  glossary: "ft.glossary",
  summary: "ov.tile.summary",
  modules: "ov.tile.modules",
  contributions: "ov.tile.contributions",
  abstract_translation: "usage.abstract",
  rerank: "rs.rerank",
  suggest_keywords: "usage.suggest",
  connection_test: "usage.test",
};
