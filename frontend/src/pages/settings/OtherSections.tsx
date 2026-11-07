import { useQueryClient } from "@tanstack/react-query";
import { Check, CheckCircle2, ChevronDown, Copy, Download, ExternalLink, HardDrive, Info, KeyRound, RefreshCw, Trash2, Upload, XCircle } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { useAiConfig, useSettings, useSources, useStatus, useUpdateSettings } from "../../api/hooks";
import type { Settings, SourceInfo, UpdateInfo } from "../../api/types";
import { useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, Field, Input, Notice, Segmented, Skeleton, Switch } from "../../components/ui/primitives";
import { LANGUAGES, cap, rich, t, useLang, type Lang } from "../../i18n";
import { copyText } from "../../lib/clipboard";
import { cn } from "../../lib/cn";
import { bytes, languageName, timeAgo } from "../../lib/format";

function Row({ title, desc, children, className }: { title: ReactNode; desc?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={cn("flex flex-wrap items-start justify-between gap-x-4 gap-y-2 py-4 first:pt-0 last:pb-0 sm:flex-nowrap", className)}>
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

// ======================= Language =======================
export function LanguageSection() {
  const { lang, setLang } = useLang();
  const { s } = useS();
  const { data: ai } = useAiConfig();
  const qc = useQueryClient();
  const out = s?.ai.output_language ?? "auto";
  const setOut = async (v: string) => {
    await api.patch("/ai/config", { output_language: v });
    qc.invalidateQueries({ queryKey: ["settings"] });
    qc.invalidateQueries({ queryKey: ["ai-config"] });
    qc.invalidateQueries({ queryKey: ["paper"] });
    qc.invalidateQueries({ queryKey: ["fulltext"] });
  };
  return (
    <div className="space-y-6">
      <Card className="p-5">
        <div className="text-[14px] font-medium text-text">{t("lang.ui")}</div>
        <div className="mt-0.5 text-[13px] text-text-3">{t("lang.ui_desc")}</div>
        <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              lang={l.locale}
              onClick={() => setLang(l.code)}
              className={cn(
                "flex items-center justify-between rounded-xl border px-3 py-2.5 text-left text-sm transition-all",
                lang === l.code ? "border-accent bg-accent-soft font-medium text-text ring-1 ring-accent" : "border-border text-text-2 hover:border-border-strong",
              )}
            >
              {l.native}
              {lang === l.code && <Check className="size-4 text-accent" />}
            </button>
          ))}
        </div>
      </Card>
      <Card className="p-5">
        <div className="text-[14px] font-medium text-text">{t("lang.output")}</div>
        <div className="mt-0.5 text-[13px] leading-relaxed text-text-3">{t("lang.output_desc")}</div>
        <Segmented<string>
          className="mt-3"
          value={out}
          onChange={setOut}
          options={[
            { value: "auto", label: t("lang.follow_ui", { language: LANGUAGES.find((l) => l.code === lang)!.native }) },
            ...LANGUAGES.map((l) => ({ value: l.code as string, label: l.native })),
          ]}
        />
        {ai?.effective_output_language && (
          <p className="mt-3 text-[12px] text-text-3">{t("lang.output_now", { language: languageName(ai.effective_output_language as Lang) })}</p>
        )}
      </Card>
      <Notice tone="neutral" icon={<Info className="size-4" />} title={t("lang.papers_title")}>
        <p className="mt-1 text-[13px] leading-relaxed">{t("lang.papers_desc")}</p>
      </Notice>
    </div>
  );
}

// ======================= Recommendation =======================
const PRESETS = ["balanced", "relevance", "quality", "fresh"] as const;
const WINDOWS = [1, 3, 7, 14, 30, 90, 180, 365];

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
    balanced: { relevance: 0.5, quality: 0.3, freshness: 0.2 },
    relevance: { relevance: 0.7, quality: 0.15, freshness: 0.15 },
    quality: { relevance: 0.45, quality: 0.4, freshness: 0.15 },
    fresh: { relevance: 0.45, quality: 0.15, freshness: 0.4 },
  };
  const halfLife = { latest: 3, balanced: 7, relaxed: 21 }[s.time_preference];
  const f = (age: number) => Math.round((0.2 + 0.8 * Math.pow(0.5, age / halfLife)) * 100);

  return (
    <div className="space-y-6">
      <Card className="divide-y divide-border p-5">
        <Row title={t("rs.count")} desc={t("rs.count_desc")}>
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
          <div className="text-[14px] font-medium text-text">{t("rs.window")}</div>
          <div className="mt-0.5 text-[13px] text-text-3">{t("rs.window_desc")}</div>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {WINDOWS.map((d) => (
              <button
                key={d}
                onClick={() => set({ window_days: d })}
                className={cn("h-8 rounded-lg px-3 text-[13px] font-medium", s.window_days === d ? "bg-accent text-white" : "bg-surface-3 text-text-2 hover:text-text")}
              >
                {t("rs.last_days", { n: d })}
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
              <Input value={custom} onChange={(e) => setCustom(e.target.value.replace(/\D/g, ""))}
                placeholder={!WINDOWS.includes(s.window_days) ? t("rs.current_days", { n: s.window_days }) : t("rs.custom_days")} className="h-8 w-36" />
              <Button size="sm" type="submit" disabled={!custom}>
                {t("common.ok")}
              </Button>
            </form>
          </div>
          <p className="mt-2 text-[12px] leading-relaxed text-text-3">{t("rs.window_per_direction")}</p>
        </div>
        <div className="pt-4">
          <div className="text-[14px] font-medium text-text">{t("rs.time_pref")}</div>
          <div className="mt-0.5 text-[13px] text-text-3">{t("rs.time_pref_desc")}</div>
          <Segmented
            className="mt-3"
            value={s.time_preference}
            onChange={(v) => set({ time_preference: v })}
            options={[
              { value: "latest", label: t("rs.pref.latest") },
              { value: "balanced", label: t("rs.pref.balanced") },
              { value: "relaxed", label: t("rs.pref.relaxed") },
            ]}
          />
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs text-text-3">
            <span>{t("rs.fresh_today", { v: f(0) })}</span>
            {[3, 7, 14, 30].map((d) => (
              <span key={d}>{t("rs.fresh_days", { n: d, v: f(d) })}</span>
            ))}
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <div className="text-[14px] font-medium text-text">{t("rs.strategy")}</div>
        <div className="mt-0.5 text-[13px] text-text-3">{t("rs.strategy_desc")}</div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {PRESETS.map((k) => {
            const on = s.ranking_preset === k;
            return (
              <button
                key={k}
                onClick={() => {
                  setW(null);
                  set({ ranking_preset: k });
                }}
                className={cn("rounded-xl border p-3 text-left transition-all", on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-border hover:border-border-strong")}
              >
                <div className="text-sm font-medium text-text">{t(`rs.preset.${k}`)}</div>
                <div className="mt-0.5 text-xs text-text-3">{t(`rs.preset.${k}.desc`)}</div>
                <WeightBars w={presets[k]} />
              </button>
            );
          })}
        </div>
        <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-text-3">
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-accent" />{t("rs.legend.relevance")}</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-[#e9a93a]" />{t("rs.legend.quality")}</span>
          <span className="flex items-center gap-1"><span className="size-2 rounded-full bg-success" />{t("rs.legend.freshness")}</span>
        </div>
        <details className="group mt-4 rounded-xl border border-border" open={s.ranking_preset === "custom"}>
          <summary className="flex cursor-pointer list-none items-center justify-between px-3 py-2.5 text-[13px] font-medium text-text">
            <span>
              {t("rs.custom")}
              {s.ranking_preset === "custom" && <Badge tone="accent" className="ml-2">{t("rs.in_use")}</Badge>}
            </span>
            <ChevronDown className="size-4 text-text-3 transition-transform group-open:rotate-180" />
          </summary>
          <div className="space-y-4 border-t border-border px-3 py-4">
            {(["relevance", "quality", "freshness"] as const).map((k) => (
              <div key={k}>
                <div className="mb-1 flex justify-between text-[13px]">
                  <span className="text-text-2">{t(`score.${k}`)}</span>
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
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs text-text-3">{t("rs.custom_note")}</span>
              <Button size="sm" variant="primary" disabled={!w} onClick={() => { set({ weights: weights }); setW(null); }}>
                {t("rs.apply")}
              </Button>
            </div>
          </div>
        </details>
      </Card>

      <Card className="divide-y divide-border p-5">
        <Row title={t("rs.prefer_reviews")} desc={t("rs.prefer_reviews_desc")}>
          <Switch checked={s.prefer_reviews} onChange={(v) => set({ prefer_reviews: v })} label={t("rs.prefer_reviews")} />
        </Row>
        <Row title={<span className="flex items-center gap-2">{t("rs.rerank")} <Badge tone="warning">{t("rs.uses_api")}</Badge></span>} desc={t("rs.rerank_desc")}>
          <Switch checked={s.ai_rerank} onChange={(v) => set({ ai_rerank: v })} label={t("rs.rerank")} />
        </Row>
        <Row title={t("rs.personalize")} desc={t("rs.personalize_desc")}>
          <Switch checked={s.personalize} onChange={(v) => set({ personalize: v })} label={t("rs.personalize")} />
        </Row>
        <Row title={t("rs.auto_fetch")} desc={t("rs.auto_fetch_desc")}>
          <Switch checked={s.auto_fetch_on_open} onChange={(v) => set({ auto_fetch_on_open: v })} label={t("rs.auto_fetch")} />
        </Row>
      </Card>

      <Card className="p-5">
        <button onClick={() => setShowAlgo(!showAlgo)} className="flex w-full items-center justify-between text-left">
          <span className="flex items-center gap-2 text-[14px] font-medium text-text">
            <Info className="size-4 text-text-3" /> {t("rs.algo")}
          </span>
          <ChevronDown className={cn("size-4 text-text-3 transition-transform", showAlgo && "rotate-180")} />
        </button>
        {showAlgo && (
          <div className="mt-4 space-y-3 text-[13px] leading-relaxed text-text-2">
            {(["rs.algo1", "rs.algo2", "rs.algo3", "rs.algo4", "rs.algo5", "rs.algo6", "rs.algo7"] as const).map((k) => (
              <p key={k}>{rich(k, {}, { b: (x) => <strong className="text-text">{x}</strong> })}</p>
            ))}
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
      toast({ tone: "error", title: t("common.save_failed"), description: errorMessage(e) });
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
            {src.key_policy === "none" && <Badge tone="success">{t("src.no_key")}</Badge>}
            {src.key_policy === "optional" && <Badge tone="neutral">{t("src.key_optional")}</Badge>}
            {src.key_policy === "recommended" && <Badge tone="warning">{t("src.key_recommended")}</Badge>}
          </div>
          <p className="mt-1 text-[13px] leading-relaxed text-text-2">{src.description}</p>
          {src.enabled && last && (
            <div className="mt-2 flex items-start gap-1.5 text-xs">
              {last.errors?.length ? (
                <>
                  <XCircle className="mt-px size-3.5 shrink-0 text-danger" />
                  <span className="text-danger">{last.errors[0]}</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="mt-px size-3.5 shrink-0 text-success" />
                  <span className="text-text-3">{t("src.last_fetch", { when: timeAgo(last.at), n: last.fetched })}</span>
                </>
              )}
            </div>
          )}
          {src.key_policy !== "none" && (
            <div className="mt-3">
              <button onClick={() => setOpen(!open)} className="flex items-center gap-1 text-xs text-text-3 hover:text-text">
                <KeyRound className="size-3.5" />
                {src.key_configured ? t("src.key_set", { key: src.key_masked ?? "" }) : t("src.add_key")}
                <ChevronDown className={cn("size-3.5 transition-transform", open && "rotate-180")} />
              </button>
              {open && (
                <div className="mt-2 space-y-2">
                  <p className="text-xs leading-relaxed text-text-3">{src.key_help}</p>
                  <div className="flex flex-wrap gap-2">
                    <Input type="password" value={key} onChange={(e) => setKey(e.target.value)} placeholder={t("src.paste_key")} className="h-8 max-w-xs font-mono" autoComplete="off" />
                    <Button size="sm" variant="primary" disabled={!key.trim()} onClick={() => { patch({ api_key: key }, t("common.saved")); setKey(""); }}>
                      {t("common.save")}
                    </Button>
                    {src.key_configured && (
                      <Button size="sm" variant="ghost" onClick={() => patch({ remove_key: true }, t("src.deleted"))}>
                        {t("common.delete")}
                      </Button>
                    )}
                    <a href={src.homepage} target="_blank" rel="noreferrer">
                      <Button size="sm" variant="ghost" icon={<ExternalLink className="size-3.5" />}>
                        {t("src.homepage")}
                      </Button>
                    </a>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
        <Switch checked={src.enabled} onChange={(v) => patch({ enabled: v })} label={t("src.enable", { name: src.name })} />
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
        {t("src.intro")}
      </Notice>
      {data.sources.map((s) => (
        <SourceCard key={s.id} src={s} />
      ))}
      <Notice tone="neutral" icon={<Info className="size-4" />} title={t("src.coverage_title")}>
        <ul className="mt-1 list-disc space-y-1 pl-4 text-[13px] leading-relaxed">
          <li>{t("src.coverage_zh")}</li>
          <li>{t("src.coverage_ja")}</li>
          <li>{t("src.coverage_ko")}</li>
          <li>{t("src.coverage_other")}</li>
        </ul>
      </Notice>
      <div className="pt-2 text-[13px] font-medium text-text-2">{t("src.signals")}</div>
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
      <Notice tone="accent" icon={<Info className="size-4" />} title={t("feat.notice_title")}>
        {t("feat.notice")}
      </Notice>
      <Card className="divide-y divide-border p-5">
        <Row title={t("ov.tile.translate")} desc={t("feat.translate_desc")}>
          <Switch checked={s.ai.features.translate} onChange={(v) => feat("translate", v)} label={t("ov.tile.translate")} />
        </Row>
        <Row title={cap(t("pp.summary.title"))} desc={t("feat.summary_desc")}>
          <Switch checked={s.ai.features.summary} onChange={(v) => feat("summary", v)} label={t("pp.summary.title")} />
        </Row>
        <Row title={cap(t("pp.modules.title"))} desc={t("feat.modules_desc")}>
          <Switch checked={s.ai.features.modules} onChange={(v) => feat("modules", v)} label={t("pp.modules.title")} />
        </Row>
        <Row title={cap(t("pp.contrib.title"))} desc={t("feat.contrib_desc")}>
          <Switch checked={s.ai.features.contributions} onChange={(v) => feat("contributions", v)} label={t("pp.contrib.title")} />
        </Row>
      </Card>
      <Card className="divide-y divide-border p-5">
        <Row title={t("feat.output_lang")} desc={t("feat.output_lang_desc")}>
          <Link to="/settings?s=language" className="text-[13px] text-accent-text hover:underline">
            {t("feat.output_lang_link")}
          </Link>
        </Row>
        <Row title={t("feat.keep_terms")} desc={t("feat.keep_terms_desc")}>
          <Switch checked={s.ai.keep_english_terms} onChange={(v) => set({ ai: { ...s.ai, keep_english_terms: v } })} label={t("feat.keep_terms")} />
        </Row>
        <Row title={t("feat.appendix")} desc={t("feat.appendix_desc")}>
          <Switch checked={s.ai.translate_appendix} onChange={(v) => set({ ai: { ...s.ai, translate_appendix: v } })} label={t("feat.appendix")} />
        </Row>
        <Row title={t("feat.concurrency")} desc={t("feat.concurrency_desc")}>
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
      <Row title={t("read.theme")} desc={t("read.theme_desc")}>
        <Segmented value={r.theme} onChange={(v) => set({ reading: { ...r, theme: v } })}
          options={[{ value: "system", label: t("theme.system") }, { value: "light", label: t("theme.light") }, { value: "dark", label: t("theme.dark") }]} />
      </Row>
      <Row title={t("read.font")} desc={t("read.font_desc")}>
        <Segmented value={r.font_size} onChange={(v) => set({ reading: { ...r, font_size: v } })}
          options={[{ value: "sm", label: t("read.small") }, { value: "md", label: t("read.medium") }, { value: "lg", label: t("read.large") }]} />
      </Row>
      <Row title={t("read.view")} desc={t("read.view_desc")}>
        <Segmented value={r.translation_view} onChange={(v) => set({ reading: { ...r, translation_view: v } })}
          options={[{ value: "en", label: t("ft.view.original") }, { value: "bilingual", label: t("ft.view.bilingual") }, { value: "zh", label: t("ft.view.translation") }]} />
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
    if (!(await confirm({ title, description, confirmText: t("data.confirm_clear"), danger: true }))) return;
    try {
      await api.post("/data/clear", { target });
      toast({ tone: "success", title: t("data.cleared") });
      refetch();
      qc.invalidateQueries();
    } catch (e) {
      toast({ tone: "error", title: t("data.clear_failed"), description: errorMessage(e) });
    }
  };

  const onImport = async (file: File) => {
    setImporting(true);
    try {
      const text = await file.text();
      const data = JSON.parse(text);
      if (!(await confirm({ title: t("data.import_q"), description: t("data.import_desc", { name: file.name }), confirmText: t("data.import") }))) return;
      const r = await api.post<{ counts: Record<string, number> }>("/data/import", data);
      toast({ tone: "success", title: t("data.imported"), description: t("data.imported_desc", { papers: r.counts.papers ?? 0, ai: r.counts.ai_results ?? 0 }) });
      qc.invalidateQueries();
    } catch (e) {
      toast({ tone: "error", title: t("data.import_failed"), description: e instanceof SyntaxError ? t("data.invalid_json") : errorMessage(e) });
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
                { l: t("data.papers"), v: st.counts.papers },
                { l: t("data.recommendations"), v: st.counts.recommendations },
                { l: t("data.ai_results"), v: st.counts.ai_results },
                { l: t("data.translated"), v: st.counts.translated_units },
              ].map((x) => (
                <div key={x.l} className="rounded-xl bg-surface-2 px-3 py-3">
                  <div className="text-xs text-text-3">{x.l}</div>
                  <div className="mt-1 text-lg font-semibold tabular-nums text-text">{x.v}</div>
                </div>
              ))}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2 text-[13px] text-text-2">
              <HardDrive className="size-4 text-text-3" />
              {t("data.dir")}
              <code className="break-all rounded bg-surface-3 px-1.5 py-0.5 font-mono text-xs">{st.data_dir}</code>
              <span className="text-text-3">({bytes(st.db_size)})</span>
              <button
                onClick={() => copyText(st.data_dir).then((ok) => ok && toast({ tone: "success", title: t("data.path_copied") }))}
                className="rounded p-1 text-text-3 hover:bg-surface-3 hover:text-text"
                aria-label={t("data.copy_path")}
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
        <Row title={t("data.export")} desc={t("data.export_desc")}>
          <a href="/api/data/export">
            <Button icon={<Download className="size-4" />}>{t("data.export_btn")}</Button>
          </a>
        </Row>
        <Row title={t("data.import_title")} desc={t("data.import_title_desc")}>
          <>
            <input ref={fileRef} type="file" accept="application/json,.json" className="hidden" onChange={(e) => e.target.files?.[0] && onImport(e.target.files[0])} />
            <Button icon={<Upload className="size-4" />} loading={importing} onClick={() => fileRef.current?.click()}>
              {t("data.import")}
            </Button>
          </>
        </Row>
      </Card>

      <Card className="divide-y divide-border p-5">
        <Row title={t("data.clear_search")} desc={t("data.clear_search_desc")}>
          <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => clear("search_cache", t("data.clear_search_q"), t("data.clear_search_confirm"))}>
            {t("data.clear")}
          </Button>
        </Row>
        <Row title={t("data.clear_fulltext")} desc={t("data.clear_fulltext_desc")}>
          <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => clear("fulltext_cache", t("data.clear_fulltext_q"), t("data.clear_fulltext_confirm"))}>
            {t("data.clear")}
          </Button>
        </Row>
        <Row title={t("data.clear_history")} desc={t("data.clear_history_desc")}>
          <Button variant="danger" icon={<Trash2 className="size-4" />} onClick={() => clear("history", t("data.clear_history_q"), t("data.clear_history_confirm"))}>
            {t("data.clear_all")}
          </Button>
        </Row>
        <Row title={t("data.reset_usage")} desc={t("data.reset_usage_desc")}>
          <Button variant="ghost" icon={<Trash2 className="size-4" />} onClick={() => clear("usage", t("data.reset_usage_q"), t("data.reset_usage_confirm"))}>
            {t("data.reset")}
          </Button>
        </Row>
      </Card>

      {st && (
        <Card className="p-5">
          <Field label={t("data.about")}>
            <div className="grid grid-cols-[110px_1fr] gap-y-1.5 text-[13px]">
              <span className="text-text-3">{t("data.version")}</span>
              <span className="text-text">
                PaperLook {st.version}
                <UpdateCheck />
              </span>
              <span className="text-text-3">{t("data.mode")}</span>
              <span className="text-text">{st.packaged ? t("data.mode_desktop") : t("data.mode_source")} · Python {st.python}</span>
              <span className="text-text-3">{t("data.secrets")}</span>
              <span className="text-text">{st.secret_backend}</span>
              <span className="text-text-3">{t("data.uptime")}</span>
              <span className="text-text">{t("data.minutes", { n: Math.floor(st.uptime_seconds / 60) })}</span>
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
      if (!r.has_update) toast({ tone: "success", title: t("upd.latest"), description: r.latest ? t("upd.latest_is", { v: r.latest }) : t("upd.none") });
    } catch (e) {
      toast({ tone: "error", title: t("upd.failed"), description: errorMessage(e) });
    } finally {
      setBusy(false);
    }
  };
  if (info?.has_update)
    return (
      <a href={info.url} target="_blank" rel="noreferrer" className="ml-2 inline-flex items-center gap-1 text-accent-text hover:underline">
        {t("upd.available", { v: info.latest ?? "" })} <ExternalLink className="size-3" />
      </a>
    );
  return (
    <button onClick={check} disabled={busy} className="ml-2 inline-flex items-center gap-1 text-xs text-text-3 hover:text-text disabled:opacity-60">
      <RefreshCw className={cn("size-3", busy && "animate-spin")} /> {t("upd.check")}
    </button>
  );
}
