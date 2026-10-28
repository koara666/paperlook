import {
  ArrowDown,
  ArrowRight,
  BadgeCheck,
  BookMarked,
  Boxes,
  CircleAlert,
  CircleHelp,
  FlaskConical,
  Gauge,
  GitBranch,
  Lightbulb,
  ListChecks,
  Microscope,
  Quote,
  Route,
  Sparkles,
  Target,
  TriangleAlert,
  Users,
  Wrench,
} from "lucide-react";
import type { ReactNode } from "react";
import { Badge, Card } from "../../components/ui/primitives";
import { cn } from "../../lib/cn";
import { MathText, MathWrap } from "../../lib/math";

// ---- tolerant accessors: model output may deviate from the schema ----
const arr = <T = any,>(v: any): T[] => (Array.isArray(v) ? v : v == null || v === "" ? [] : [v]);
const str = (v: any): string => (v == null ? "" : typeof v === "string" ? v : typeof v === "object" ? Object.values(v).join("；") : String(v));
const isEmptyText = (s: string) => !s || /^(无|暂无|n\/?a|none|null)$/i.test(s.trim());

function Block({ icon, title, children, className, tone }: { icon: ReactNode; title: string; children: ReactNode; className?: string; tone?: "accent" | "warning" }) {
  return (
    <Card className={cn("p-5", className)}>
      <h3 className="mb-3 flex items-center gap-2 text-[15px] font-semibold text-text">
        <span className={cn("flex size-7 items-center justify-center rounded-lg", tone === "warning" ? "bg-warning-soft text-warning" : "bg-accent-soft text-accent-text")}>{icon}</span>
        {title}
      </h3>
      <div className="space-y-3 text-[14.5px] leading-[1.8] text-text-2">{children}</div>
    </Card>
  );
}

function Labeled({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="mb-0.5 text-xs font-medium text-text-3">{label}</div>
      <div className="text-text">{children}</div>
    </div>
  );
}

function Bullets({ items, className }: { items: any[]; className?: string }) {
  const list = items.map(str).filter((s) => !isEmptyText(s));
  if (!list.length) return <p className="text-text-3">论文未明确说明</p>;
  return (
    <ul className={cn("space-y-1.5", className)}>
      {list.map((t, i) => (
        <li key={i} className="flex gap-2.5">
          <span className="mt-[11px] size-1.5 shrink-0 rounded-full bg-accent/60" />
          <span className="text-text">
            <MathText text={t} />
          </span>
        </li>
      ))}
    </ul>
  );
}

function Chips({ items }: { items: any[] }) {
  const list = items.map(str).filter((s) => !isEmptyText(s));
  if (!list.length) return <span className="text-text-3">论文未明确说明</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {list.map((t) => (
        <span key={t} className="rounded-md border border-border bg-surface-2 px-2 py-0.5 text-[13px] text-text">
          {t}
        </span>
      ))}
    </div>
  );
}

// ======================= Summary =======================
export function SummaryView({ c }: { c: any }) {
  const problem = c.problem ?? {};
  const method = c.method ?? {};
  const exp = c.experiments ?? {};
  const advice = c.reading_advice ?? {};
  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-accent/20 bg-gradient-to-br from-accent-soft to-surface p-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <Badge tone="accent" icon={<Sparkles className="size-3" />}>
            一句话总结
          </Badge>
          {c.paper_type && <Badge tone="outline">{str(c.paper_type)}</Badge>}
        </div>
        <p className="text-[17px] font-medium leading-relaxed text-text">
          <MathText text={str(c.tldr)} />
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Block icon={<Target className="size-4" />} title="研究问题">
          <Labeled label="要解决什么问题">
            <MathText text={str(problem.question) || "论文未明确说明"} />
          </Labeled>
          <Labeled label="为什么值得研究">
            <MathText text={str(problem.importance) || "论文未明确说明"} />
          </Labeled>
        </Block>
        <Block icon={<Wrench className="size-4" />} title="研究方法">
          <Labeled label="技术路线">
            <MathText text={str(method.overview) || "论文未明确说明"} />
          </Labeled>
          <Labeled label="核心思想">
            <MathText text={str(method.core_idea) || "论文未明确说明"} />
          </Labeled>
          {method.relation_to_prior && (
            <Labeled label="与已有方法的关系">
              <MathText text={str(method.relation_to_prior)} />
            </Labeled>
          )}
        </Block>
      </div>

      <Block icon={<FlaskConical className="size-4" />} title="实验与结果">
        <div className="grid gap-4 sm:grid-cols-2">
          <Labeled label="数据集 / 实验环境">
            <Chips items={arr(exp.datasets)} />
          </Labeled>
          <Labeled label="评价指标">
            <Chips items={arr(exp.metrics)} />
          </Labeled>
        </div>
        <Labeled label="主要结果">
          <Bullets items={arr(exp.main_results)} />
        </Labeled>
        {exp.evidence_assessment && (
          <div className="rounded-xl bg-surface-2 px-4 py-3">
            <div className="mb-0.5 flex items-center gap-1.5 text-xs font-medium text-text-3">
              <Gauge className="size-3.5" /> 实验是否充分（AI 评估）
            </div>
            <div className="text-text">
              <MathText text={str(exp.evidence_assessment)} />
            </div>
          </div>
        )}
      </Block>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Block icon={<ListChecks className="size-4" />} title="主要结论">
          <Bullets items={arr(c.conclusions)} />
        </Block>
        <Block icon={<Lightbulb className="size-4" />} title="值得关注">
          <Bullets items={arr(c.highlights)} />
        </Block>
      </div>

      <Block icon={<TriangleAlert className="size-4" />} title="局限性" tone="warning">
        {arr(c.limitations).length ? (
          <ul className="space-y-2">
            {arr(c.limitations).map((l: any, i) => {
              const point = typeof l === "string" ? l : str(l.point);
              const src = typeof l === "object" ? l.source : null;
              return (
                <li key={i} className="flex items-start gap-2.5">
                  <Badge tone={src === "author" ? "neutral" : "warning"} className="mt-0.5 shrink-0">
                    {src === "author" ? "作者承认" : "AI 评估"}
                  </Badge>
                  <span className="text-text">
                    <MathText text={point} />
                  </span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-text-3">论文未明确说明</p>
        )}
      </Block>

      <Block icon={<Route className="size-4" />} title="阅读建议">
        {arr(advice.audience).length > 0 && (
          <Labeled label="适合的研究方向">
            <Chips items={arr(advice.audience)} />
          </Labeled>
        )}
        {arr(advice.priority_sections).length > 0 && (
          <Labeled label="优先阅读的章节">
            <ul className="space-y-1.5">
              {arr(advice.priority_sections).map((p: any, i) => (
                <li key={i} className="flex gap-2">
                  <BookMarked className="mt-1 size-3.5 shrink-0 text-accent" />
                  <span>
                    <span className="font-medium text-text">{typeof p === "string" ? p : str(p.section)}</span>
                    {p?.reason && <span className="text-text-2"> — {str(p.reason)}</span>}
                  </span>
                </li>
              ))}
            </ul>
          </Labeled>
        )}
        {advice.quick_path && (
          <Labeled label="快速理解路径">
            <MathText text={str(advice.quick_path)} />
          </Labeled>
        )}
      </Block>
    </div>
  );
}

// ======================= Modules =======================
const NOVELTY: Record<string, { label: string; tone: "accent" | "success" | "neutral" }> = {
  new: { label: "本文提出", tone: "accent" },
  adapted: { label: "改进已有方法", tone: "success" },
  existing: { label: "沿用已有方法", tone: "neutral" },
};

function flowChain(flow: any[]): string[] | null {
  // If the edges form a simple path, show it as a chain.
  // Self-loops (a module "flowing" into itself, seen from Gemini) are shown as plain items, not edges.
  const edges = flow.filter((f) => f && f.from && f.to && str(f.from) !== str(f.to)).map((f) => [str(f.from), str(f.to)]);
  if (!edges.length) return null;
  const outs = new Map(edges.map(([a, b]) => [a, b]));
  const ins = new Set(edges.map(([, b]) => b));
  const start = edges.map(([a]) => a).find((a) => !ins.has(a));
  if (!start || outs.size !== edges.length) return null;
  const chain = [start];
  const seen = new Set(chain);
  while (outs.has(chain[chain.length - 1])) {
    const nx = outs.get(chain[chain.length - 1])!;
    if (seen.has(nx)) return null;
    chain.push(nx);
    seen.add(nx);
  }
  return chain.length === edges.length + 1 ? chain : null;
}

export function ModulesView({ c }: { c: any }) {
  const modules = arr(c.modules);
  const flow = arr(c.flow);
  const chain = flowChain(flow);
  if (c.applicable === false) {
    return (
      <div className="space-y-4">
        <Card className="p-5">
          <div className="flex items-start gap-3">
            <CircleHelp className="mt-0.5 size-5 shrink-0 text-text-3" />
            <div>
              <div className="font-semibold text-text">这篇论文没有可拆分的技术模块</div>
              <p className="mt-1 text-sm leading-relaxed text-text-2">{str(c.reason)}</p>
            </div>
          </div>
        </Card>
        {arr(c.structure).length > 0 && (
          <Block icon={<GitBranch className="size-4" />} title="论文的核心论证结构">
            <ol className="space-y-2">
              {arr(c.structure).map((s, i) => (
                <li key={i} className="flex gap-3">
                  <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-surface-3 text-xs font-semibold text-text-2">{i + 1}</span>
                  <span className="text-text">
                    <MathText text={str(s)} />
                  </span>
                </li>
              ))}
            </ol>
          </Block>
        )}
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {c.overview && (
        <Block icon={<Boxes className="size-4" />} title="整体架构">
          <p className="text-text">
            <MathText text={str(c.overview)} />
          </p>
        </Block>
      )}

      {flow.length > 0 && (
        <Card className="p-5">
          <h3 className="mb-4 flex items-center gap-2 text-[15px] font-semibold text-text">
            <span className="flex size-7 items-center justify-center rounded-lg bg-accent-soft text-accent-text">
              <GitBranch className="size-4" />
            </span>
            模块协作流程
          </h3>
          {chain ? (
            <div className="flex flex-col items-stretch gap-1 sm:flex-row sm:flex-wrap sm:items-center sm:gap-2">
              {chain.map((n, i) => (
                <div key={n + i} className="flex flex-col items-center gap-1 sm:flex-row sm:gap-2">
                  <span className="rounded-xl border border-accent/25 bg-accent-soft px-3 py-2 text-center text-[13px] font-medium text-accent-text">{n}</span>
                  {i < chain.length - 1 && (
                    <>
                      <ArrowRight className="hidden size-4 text-text-3 sm:block" />
                      <ArrowDown className="size-4 text-text-3 sm:hidden" />
                    </>
                  )}
                </div>
              ))}
            </div>
          ) : null}
          <ul className={cn("space-y-3 text-[14px]", chain && "mt-4 border-t border-border pt-4")}>
            {flow.map((f: any, i) => (
              <li key={i}>
                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                  <span className="font-medium text-text">{str(f.from)}</span>
                  {str(f.to) !== str(f.from) && (
                    <>
                      <ArrowRight className="size-3.5 translate-y-0.5 text-text-3" />
                      <span className="font-medium text-text">{str(f.to)}</span>
                    </>
                  )}
                </div>
                {f.description && (
                  <p className="mt-0.5 leading-relaxed text-text-2">
                    <MathText text={str(f.description)} />
                  </p>
                )}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {modules.map((m: any, i) => {
          const nov = NOVELTY[str(m.novelty)] ?? null;
          return (
            <Card key={i} className="flex flex-col p-5">
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                {m.category && <Badge tone="outline">{str(m.category)}</Badge>}
                {nov && <Badge tone={nov.tone}>{nov.label}</Badge>}
                {m.section && <span className="ml-auto text-xs text-text-3">§ {str(m.section)}</span>}
              </div>
              <h4 className="text-[16px] font-semibold text-text">
                {str(m.name)}
                {m.name_en && str(m.name_en) !== str(m.name) && <span className="ml-2 font-serif text-sm font-normal text-text-3">{str(m.name_en)}</span>}
              </h4>
              {m.role && <p className="mt-1.5 text-[14px] leading-relaxed text-text-2">{str(m.role)}</p>}
              {(m.inputs || m.outputs) && (
                <div className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 rounded-lg bg-surface-2 px-3 py-2 text-[13px]">
                  <span className="text-text-3">输入</span>
                  <span className="text-text">
                    <MathText text={str(m.inputs) || "—"} />
                  </span>
                  <span className="text-text-3">输出</span>
                  <span className="text-text">
                    <MathText text={str(m.outputs) || "—"} />
                  </span>
                </div>
              )}
              {m.mechanism && (
                <p className="mt-3 text-[14px] leading-[1.8] text-text">
                  <MathText text={str(m.mechanism)} />
                </p>
              )}
              {m.key_formula && str(m.key_formula).trim() && (
                <div className="mt-3 overflow-x-auto rounded-lg border border-border px-3 py-2">
                  <MathWrap className="text-center leading-loose" latex={str(m.key_formula).replace(/^\$+|\$+$/g, "")} />
                </div>
              )}
            </Card>
          );
        })}
      </div>

      {arr(c.design_insights).length > 0 && (
        <Block icon={<Lightbulb className="size-4" />} title="关键设计选择">
          <Bullets items={arr(c.design_insights)} />
        </Block>
      )}
    </div>
  );
}

// ======================= Contributions =======================
const VERIFY: Record<string, { label: string; tone: "success" | "warning" | "danger" | "neutral"; icon: ReactNode }> = {
  exact: { label: "原文已核验", tone: "success", icon: <BadgeCheck className="size-3" /> },
  close: { label: "与原文基本一致", tone: "success", icon: <BadgeCheck className="size-3" /> },
  partial: { label: "仅部分匹配原文", tone: "warning", icon: <CircleAlert className="size-3" /> },
  not_found: { label: "未能在原文中找到", tone: "danger", icon: <CircleAlert className="size-3" /> },
  missing: { label: "缺少原文引用", tone: "neutral", icon: <CircleAlert className="size-3" /> },
};

const STRENGTH: Record<string, { label: string; w: string }> = {
  strong: { label: "强", w: "w-full" },
  moderate: { label: "中", w: "w-2/3" },
  weak: { label: "弱", w: "w-1/3" },
};

function TierHeader({ n, title, desc, tone }: { n: number; title: string; desc: string; tone: "accent" | "success" | "warning" }) {
  const cls = { accent: "bg-accent text-white", success: "bg-success text-white", warning: "bg-warning text-white" }[tone];
  return (
    <div className="mb-3 flex items-start gap-3">
      <span className={cn("flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold", cls)}>{n}</span>
      <div>
        <h3 className="text-[15px] font-semibold text-text">{title}</h3>
        <p className="text-xs text-text-3">{desc}</p>
      </div>
    </div>
  );
}

export function ContributionsView({ c }: { c: any }) {
  const explicit = arr(c.explicit);
  const derived = arr(c.derived);
  const inferred = arr(c.inferred);
  return (
    <div className="space-y-4">
      {c.problem_solved && (
        <div className="rounded-2xl border border-accent/20 bg-gradient-to-br from-accent-soft to-surface p-5">
          <Badge tone="accent" icon={<Target className="size-3" />}>
            解决的核心问题
          </Badge>
          <p className="mt-2 text-[16px] font-medium leading-relaxed text-text">
            <MathText text={str(c.problem_solved)} />
          </p>
        </div>
      )}

      <Card className="p-5">
        <TierHeader n={1} tone="accent" title="作者明确声明的贡献" desc="摘录自论文原文，并自动核对引用是否真实存在于全文中" />
        {explicit.length ? (
          <ul className="space-y-4">
            {explicit.map((e: any, i) => {
              const v = VERIFY[e.verified as string];
              return (
                <li key={i} className="rounded-xl border border-border p-4">
                  <div className="text-[15px] font-medium leading-relaxed text-text">
                    <MathText text={str(e.claim)} />
                  </div>
                  {e.quote && (
                    <blockquote className="mt-2.5 flex gap-2 border-l-2 border-accent/40 pl-3 font-serif text-[14.5px] italic leading-relaxed text-text-2">
                      <Quote className="mt-1 size-3.5 shrink-0 not-italic text-text-3" />
                      <MathText text={str(e.quote)} />
                    </blockquote>
                  )}
                  <div className="mt-2.5 flex flex-wrap items-center gap-2">
                    {v && (
                      <Badge tone={v.tone} icon={v.icon}>
                        {v.label}
                      </Badge>
                    )}
                    {e.section && <span className="text-xs text-text-3">§ {str(e.section)}</span>}
                  </div>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="text-sm text-text-3">未找到作者逐条声明的贡献。</p>
        )}
      </Card>

      <Card className="p-5">
        <TierHeader n={2} tone="success" title="基于论文内容归纳的贡献" desc="AI 根据方法与实验内容总结，作者未必逐条声明" />
        {derived.length ? (
          <ul className="space-y-3">
            {derived.map((d: any, i) => (
              <li key={i} className="flex gap-2.5">
                <span className="mt-[11px] size-1.5 shrink-0 rounded-full bg-success" />
                <div>
                  <div className="text-[14.5px] leading-relaxed text-text">
                    <MathText text={typeof d === "string" ? d : str(d.point)} />
                  </div>
                  {d?.basis && <div className="mt-0.5 text-xs text-text-3">依据：{str(d.basis)}</div>}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-3">无</p>
        )}
      </Card>

      {(arr(c.improvements).length > 0 || arr(c.new_methods).length > 0) && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          {arr(c.improvements).length > 0 && (
            <Block icon={<ArrowRight className="size-4" />} title="相比已有方法的改进">
              <ul className="space-y-3">
                {arr(c.improvements).map((m: any, i) => (
                  <li key={i}>
                    <div className="font-medium text-text">{str(m.aspect ?? m)}</div>
                    {m.detail && <div className="text-[14px] text-text-2"><MathText text={str(m.detail)} /></div>}
                    {m.evidence && <div className="mt-0.5 text-xs text-text-3">证据：<MathText text={str(m.evidence)} /></div>}
                  </li>
                ))}
              </ul>
            </Block>
          )}
          {arr(c.new_methods).length > 0 && (
            <Block icon={<Sparkles className="size-4" />} title="新提出的方法 / 模型 / 数据集">
              <ul className="space-y-3">
                {arr(c.new_methods).map((m: any, i) => (
                  <li key={i}>
                    <div className="font-serif font-semibold text-text">{str(m.name ?? m)}</div>
                    {m.description && <div className="text-[14px] text-text-2"><MathText text={str(m.description)} /></div>}
                  </li>
                ))}
              </ul>
            </Block>
          )}
        </div>
      )}

      {arr(c.experimental_support).length > 0 && (
        <Block icon={<Microscope className="size-4" />} title="实验支撑的结论">
          <ul className="space-y-3">
            {arr(c.experimental_support).map((s: any, i) => {
              const st = STRENGTH[str(s.strength)];
              return (
                <li key={i} className="grid gap-1 sm:grid-cols-[1fr_auto] sm:gap-4">
                  <div>
                    <div className="font-medium text-text"><MathText text={str(s.claim ?? s)} /></div>
                    {s.evidence && <div className="text-[13.5px] text-text-2"><MathText text={str(s.evidence)} /></div>}
                  </div>
                  {st && (
                    <div className="flex items-center gap-2 text-xs text-text-3 sm:w-28">
                      <span>支撑{st.label}</span>
                      <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-3">
                        <span className={cn("block h-full rounded-full bg-success", st.w)} />
                      </span>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </Block>
      )}

      <Card className="border-warning/30 p-5">
        <TierHeader n={3} tone="warning" title="AI 推断的潜在价值" desc="这是 AI 的推测，并非论文内容或作者观点，请谨慎参考" />
        {inferred.length ? (
          <ul className="space-y-3">
            {inferred.map((d: any, i) => (
              <li key={i} className="flex gap-2.5">
                <Users className="mt-1 size-3.5 shrink-0 text-warning" />
                <div>
                  <div className="text-[14.5px] leading-relaxed text-text"><MathText text={typeof d === "string" ? d : str(d.point)} /></div>
                  {d?.rationale && <div className="mt-0.5 text-xs text-text-3">推断理由：{str(d.rationale)}</div>}
                </div>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-text-3">无</p>
        )}
      </Card>
    </div>
  );
}
