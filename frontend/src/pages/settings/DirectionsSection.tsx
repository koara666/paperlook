import { ChevronDown, Compass, Info, Pencil, Plus, Sparkles, Trash2, Wand2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, errorMessage } from "../../api/client";
import { useAiConfig, useDirectionMutations, useDirections, useMeta, useSettings } from "../../api/hooks";
import type { Direction } from "../../api/types";
import { ChipInput } from "../../components/ui/ChipInput";
import { Dialog, MenuItem, Popover, useConfirm, useToast } from "../../components/ui/overlay";
import { Badge, Button, Card, EmptyState, Field, Input, Notice, Segmented, Skeleton, Switch } from "../../components/ui/primitives";
import { joinList, t, useLang } from "../../i18n";
import { cn } from "../../lib/cn";

const WEIGHT_KEYS = ["dir.w1", "dir.w2", "dir.w3", "dir.w4", "dir.w5"] as const;
const WINDOW_CHOICES = [0, 7, 30, 90, 180, 365];

type Draft = {
  id?: number;
  name: string;
  keywords: string[];
  exclude: string[];
  categories: string[];
  languages: string[];
  fields: string[];
  window_days: number | null;
  weight: number;
  enabled: boolean;
};
const EMPTY: Draft = { name: "", keywords: [], exclude: [], categories: [], languages: [], fields: [], window_days: null, weight: 3, enabled: true };

const hasHan = (s: string) => /[㐀-鿿]/.test(s);
const hasKana = (s: string) => /[぀-ヿ]/.test(s);
const hasHangul = (s: string) => /[가-힯]/.test(s);

/** What the sources can and cannot find for the keyword scripts used (CNKI etc. have no open API). */
function CoverageNotice({ keywords, languages }: { keywords: string[]; languages: string[] }) {
  const text = keywords.join(" ");
  const zh = (hasHan(text) && !hasKana(text)) || languages.includes("zh");
  const ja = hasKana(text) || languages.includes("ja");
  const ko = hasHangul(text) || languages.includes("ko");
  if (!zh && !ja && !ko) return null;
  return (
    <Notice tone="neutral" icon={<Info className="size-4" />} title={t("dir.coverage.title")}>
      <ul className="mt-1 space-y-1 text-[13px] leading-relaxed">
        {zh && <li>{t("dir.coverage.zh")}</li>}
        {(ja || hasHan(text)) && <li>{t("dir.coverage.ja")}</li>}
        {ko && <li>{t("dir.coverage.ko")}</li>}
      </ul>
    </Notice>
  );
}

function ChoiceChips({ options, value, onChange }: { options: { id: string; name: string }[]; value: string[]; onChange: (v: string[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {options.map((o) => {
        const on = value.includes(o.id);
        return (
          <button
            key={o.id}
            onClick={() => onChange(on ? value.filter((x) => x !== o.id) : [...value, o.id])}
            className={cn(
              "rounded-lg border px-2 py-1 text-xs transition-colors",
              on ? "border-accent bg-accent-soft text-accent-text" : "border-border text-text-2 hover:border-border-strong",
            )}
          >
            {o.name}
          </button>
        );
      })}
    </div>
  );
}

function DirectionDialog({ open, initial, onClose }: { open: boolean; initial: Draft; onClose: () => void }) {
  const [d, setD] = useState<Draft>(initial);
  const [adv, setAdv] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [customWindow, setCustomWindow] = useState("");
  const { data: meta } = useMeta();
  const { data: ai } = useAiConfig();
  const { data: settings } = useSettings();
  const { create, update } = useDirectionMutations();
  const toast = useToast();
  useEffect(() => {
    if (open) {
      setD(initial);
      setAdv(initial.categories.length > 0 || initial.exclude.length > 0 || initial.fields.length > 0);
      setCustomWindow("");
    }
  }, [open, initial]);

  const suggest = async () => {
    if (!d.name.trim()) return toast({ tone: "info", title: t("dir.name_first") });
    setSuggesting(true);
    try {
      const r = await api.post<{ keywords: string[]; exclude: string[]; categories: string[]; fields: string[]; window_days: number | null }>(
        "/directions/suggest",
        { name: d.name },
      );
      setD((x) => ({
        ...x,
        keywords: Array.from(new Set([...x.keywords, ...r.keywords])),
        exclude: x.exclude.length ? x.exclude : r.exclude,
        categories: x.categories.length ? x.categories : r.categories,
        fields: x.fields.length ? x.fields : r.fields ?? [],
        window_days: x.window_days ?? (r.window_days && r.window_days !== settings?.window_days ? r.window_days : null),
      }));
      if (r.categories.length || r.fields?.length) setAdv(true);
      toast({ tone: "success", title: t("dir.suggested", { n: r.keywords.length }), description: t("dir.suggested_desc") });
    } catch (e) {
      toast({ tone: "error", title: t("dir.suggest_failed"), description: errorMessage(e) });
    } finally {
      setSuggesting(false);
    }
  };

  const save = () => {
    const body = { ...d, name: d.name.trim() };
    const opts = {
      onSuccess: () => {
        toast({ tone: "success", title: d.id ? t("dir.saved") : t("dir.added") });
        onClose();
      },
      onError: (e: unknown) => toast({ tone: "error", title: t("common.save_failed"), description: errorMessage(e) }),
    };
    if (d.id) update.mutate({ ...body, id: d.id }, opts);
    else create.mutate(body, opts);
  };

  const windowValue = d.window_days ?? 0;
  const windowOptions = WINDOW_CHOICES.map((w) => ({ value: w, label: w === 0 ? t("dir.window.global", { n: settings?.window_days ?? 7 }) : t("today.ctl.days", { n: w }) }));
  if (windowValue && !WINDOW_CHOICES.includes(windowValue)) windowOptions.push({ value: windowValue, label: t("today.ctl.days", { n: windowValue }) });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={d.id ? t("dir.edit") : t("dir.add")}
      description={t("dir.dialog_desc")}
      width="max-w-xl"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button variant="primary" onClick={save} disabled={!d.name.trim()} loading={create.isPending || update.isPending}>
            {t("common.save")}
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Field label={t("dir.name")}>
          <Input value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} placeholder={t("dir.name_placeholder")} autoFocus />
        </Field>
        <Field
          label={t("dir.keywords")}
          extra={
            ai?.configured ? (
              <Button size="xs" variant="soft" icon={<Wand2 className="size-3.5" />} loading={suggesting} onClick={suggest}>
                {t("dir.suggest")}
              </Button>
            ) : undefined
          }
          hint={t("dir.keywords_hint")}
        >
          <ChipInput value={d.keywords} onChange={(v) => setD({ ...d, keywords: v })} placeholder={t("dir.keywords_placeholder")} />
        </Field>
        <CoverageNotice keywords={d.keywords} languages={d.languages} />
        <Field label={t("dir.window")} hint={t("dir.window_hint")}>
          <div className="space-y-2">
            <Segmented size="sm" value={windowValue} onChange={(v) => setD({ ...d, window_days: v || null })} options={windowOptions} />
            <form
              className="flex max-w-[260px] gap-1.5"
              onSubmit={(e) => {
                e.preventDefault();
                const n = parseInt(customWindow, 10);
                if (n >= 1 && n <= 1095) {
                  setD({ ...d, window_days: n });
                  setCustomWindow("");
                }
              }}
            >
              <Input value={customWindow} onChange={(e) => setCustomWindow(e.target.value.replace(/\D/g, ""))} placeholder={t("dir.window_custom")} className="h-8" />
              <Button size="sm" type="submit">
                {t("common.ok")}
              </Button>
            </form>
          </div>
        </Field>
        <Field label={t("dir.languages")} hint={t("dir.languages_hint")}>
          <ChoiceChips options={(meta?.paper_languages ?? []).map((l) => ({ id: l.code, name: l.name }))} value={d.languages} onChange={(v) => setD({ ...d, languages: v })} />
        </Field>
        <Field label={t("dir.weight")} hint={t("dir.weight_hint")}>
          <Segmented size="sm" value={d.weight} onChange={(v) => setD({ ...d, weight: v })} options={WEIGHT_KEYS.map((k, i) => ({ value: i + 1, label: t(k) }))} />
        </Field>
        <button onClick={() => setAdv(!adv)} className="flex items-center gap-1 text-xs text-text-3 hover:text-text">
          <ChevronDown className={cn("size-3.5 transition-transform", adv && "rotate-180")} /> {t("dir.advanced")}
        </button>
        {adv && (
          <div className="space-y-5">
            <Field label={t("dir.fields")} hint={t("dir.fields_hint")}>
              <ChoiceChips options={meta?.fields ?? []} value={d.fields} onChange={(v) => setD({ ...d, fields: v })} />
            </Field>
            <Field label={t("dir.exclude")} hint={t("dir.exclude_hint")}>
              <ChipInput tone="danger" value={d.exclude} onChange={(v) => setD({ ...d, exclude: v })} placeholder={t("dir.exclude_placeholder")} />
            </Field>
            <Field label={t("dir.categories")} hint={t("dir.categories_hint")}>
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
  const { lang } = useLang();
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
  const fieldName = (id: string) => meta?.fields.find((f) => f.id === id)?.name ?? id;
  const langName = (code: string) => meta?.paper_languages.find((l) => l.code === code)?.name ?? code;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="primary" icon={<Plus className="size-4" />} onClick={() => setDialog(EMPTY)}>
          {t("dir.add")}
        </Button>
        {presetsLeft.length > 0 && (
          <Popover
            className="max-h-[420px] w-[300px] overflow-y-auto"
            trigger={({ toggle }) => (
              <Button icon={<Sparkles className="size-4" />} onClick={toggle}>
                {t("dir.from_preset")}
              </Button>
            )}
          >
            {(close) =>
              (meta?.preset_groups ?? []).map((g) => {
                const items = presetsLeft.filter((p) => p.group === g.id);
                if (!items.length) return null;
                return (
                  <div key={g.id}>
                    <div className="px-2.5 pb-1 pt-2 text-[11px] font-medium text-text-3">{g.name}</div>
                    {items.map((p) => (
                      <MenuItem
                        key={p.key}
                        hint={lang !== "en" ? p.name_en : undefined}
                        onClick={() => {
                          close();
                          addPresets.mutate([p.key], { onSuccess: () => toast({ tone: "success", title: t("dir.preset_added", { name: p.name }) }) });
                        }}
                      >
                        {p.name}
                      </MenuItem>
                    ))}
                  </div>
                );
              })
            }
          </Popover>
        )}
      </div>

      {!data?.length ? (
        <Card>
          <EmptyState icon={<Compass className="size-6" />} title={t("dir.empty")} description={t("dir.empty_desc")} />
        </Card>
      ) : (
        data.map((d: Direction) => (
          <Card key={d.id} className={cn("p-4 transition-opacity sm:p-5", !d.enabled && "opacity-60")}>
            <div className="flex items-start gap-4">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-[15px] font-semibold text-text">{d.name}</h3>
                  <Badge tone="neutral">{t("dir.weight_badge", { level: t(WEIGHT_KEYS[d.weight - 1] ?? "dir.w3") })}</Badge>
                  {d.window_days ? <Badge tone="outline">{t("dir.window_badge", { n: d.window_days })}</Badge> : null}
                  {!d.enabled && <Badge tone="outline">{t("dir.disabled")}</Badge>}
                </div>
                <div className="mt-2.5 flex flex-wrap gap-1.5">
                  {d.keywords.length ? (
                    d.keywords.map((k) => (
                      <span key={k} className="rounded-md bg-accent-soft px-1.5 py-0.5 text-xs text-accent-text">
                        {k}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-text-3">{t("dir.no_keywords")}</span>
                  )}
                </div>
                {(d.exclude.length > 0 || d.categories.length > 0 || d.languages.length > 0 || d.fields.length > 0) && (
                  <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-text-3">
                    {d.languages.length > 0 && <span>{t("dir.languages_line", { list: joinList(d.languages.map(langName)) })}</span>}
                    {d.fields.length > 0 && <span>{t("dir.fields_line", { list: joinList(d.fields.map(fieldName)) })}</span>}
                    {d.exclude.length > 0 && <span>{t("dir.exclude_line", { list: joinList(d.exclude) })}</span>}
                    {d.categories.length > 0 && <span className="font-mono">arXiv: {d.categories.join(" ")}</span>}
                  </div>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Switch checked={d.enabled} onChange={(v) => update.mutate({ id: d.id, enabled: v })} label={t("dir.enable")} />
                <button className="ml-2 rounded-lg p-1.5 text-text-3 hover:bg-surface-3 hover:text-text" onClick={() => setDialog({ ...d })} aria-label={t("common.edit")}>
                  <Pencil className="size-4" />
                </button>
                <button
                  className="rounded-lg p-1.5 text-text-3 hover:bg-danger-soft hover:text-danger"
                  aria-label={t("common.delete")}
                  onClick={async () => {
                    if (await confirm({ title: t("dir.delete_q", { name: d.name }), description: t("dir.delete_desc"), confirmText: t("common.delete"), danger: true })) remove.mutate(d.id);
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
