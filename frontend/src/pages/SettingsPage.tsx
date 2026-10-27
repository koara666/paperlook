import { Bot, Compass, Database, Globe, Palette, SlidersHorizontal, ToggleRight } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { cn } from "../lib/cn";
import { AiSection } from "./settings/AiSection";
import { DirectionsSection } from "./settings/DirectionsSection";
import { DataSection, FeaturesSection, ReadingSection, RecommendSection, SourcesSection } from "./settings/OtherSections";

const SECTIONS = [
  { key: "ai", label: "AI 服务", icon: Bot, desc: "DeepSeek API 配置" },
  { key: "directions", label: "研究方向", icon: Compass, desc: "关注的领域与关键词" },
  { key: "recommend", label: "推荐设置", icon: SlidersHorizontal, desc: "数量、时间与排序" },
  { key: "sources", label: "论文来源", icon: Globe, desc: "选择检索的数据库" },
  { key: "features", label: "AI 功能", icon: ToggleRight, desc: "功能开关与翻译偏好" },
  { key: "reading", label: "阅读与外观", icon: Palette, desc: "主题与字号" },
  { key: "data", label: "数据与系统", icon: Database, desc: "备份、缓存与状态" },
] as const;

type Key = (typeof SECTIONS)[number]["key"];

export default function SettingsPage() {
  const [params, setParams] = useSearchParams();
  const current = (params.get("s") as Key) || "ai";
  const sec = SECTIONS.find((s) => s.key === current) ?? SECTIONS[0];

  return (
    <div className="mx-auto max-w-[1080px] px-4 pb-24 pt-6 sm:px-6 lg:pt-10">
      <h1 className="mb-6 text-[28px] font-semibold tracking-tight text-text">设置</h1>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-[210px_minmax(0,1fr)] md:gap-8">
        <nav className="-mx-4 flex gap-1 overflow-x-auto px-4 md:mx-0 md:flex-col md:overflow-visible md:px-0">
          {SECTIONS.map((s) => (
            <button
              key={s.key}
              onClick={() => setParams({ s: s.key })}
              className={cn(
                "flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                current === s.key ? "bg-surface font-medium text-text shadow-soft ring-1 ring-border" : "text-text-2 hover:bg-surface-3 hover:text-text",
              )}
            >
              <s.icon className={cn("size-4", current === s.key ? "text-accent" : "text-text-3")} />
              {s.label}
            </button>
          ))}
        </nav>
        <div className="min-w-0 animate-fade-in" key={current}>
          <div className="mb-5">
            <h2 className="text-lg font-semibold text-text">{sec.label}</h2>
            <p className="text-[13px] text-text-3">{sec.desc}</p>
          </div>
          {current === "ai" && <AiSection />}
          {current === "directions" && <DirectionsSection />}
          {current === "recommend" && <RecommendSection />}
          {current === "sources" && <SourcesSection />}
          {current === "features" && <FeaturesSection />}
          {current === "reading" && <ReadingSection />}
          {current === "data" && <DataSection />}
        </div>
      </div>
    </div>
  );
}
