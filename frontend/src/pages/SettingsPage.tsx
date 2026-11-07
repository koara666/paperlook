import { Bot, Compass, Database, Globe, Languages, Palette, SlidersHorizontal, ToggleRight } from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { useT } from "../i18n";
import { cn } from "../lib/cn";
import { AiSection } from "./settings/AiSection";
import { DirectionsSection } from "./settings/DirectionsSection";
import { DataSection, FeaturesSection, LanguageSection, ReadingSection, RecommendSection, SourcesSection } from "./settings/OtherSections";

const KEYS = ["language", "ai", "directions", "recommend", "sources", "features", "reading", "data"] as const;
type Key = (typeof KEYS)[number];
const ICONS = { language: Languages, ai: Bot, directions: Compass, recommend: SlidersHorizontal, sources: Globe, features: ToggleRight, reading: Palette, data: Database };

export default function SettingsPage() {
  const t = useT();
  const [params, setParams] = useSearchParams();
  const current = (KEYS as readonly string[]).includes(params.get("s") ?? "") ? (params.get("s") as Key) : "language";
  const sections = KEYS.map((key) => ({ key, label: t(`set.${key}`), desc: t(`set.${key}.desc`), icon: ICONS[key] }));
  const sec = sections.find((s) => s.key === current) ?? sections[0];

  return (
    <div className="mx-auto max-w-[1080px] px-4 pb-24 pt-6 sm:px-6 lg:pt-2">
      <h1 className="mb-6 text-[28px] font-semibold tracking-tight text-text">{t("nav.settings")}</h1>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-[210px_minmax(0,1fr)] md:gap-8">
        <nav className="-mx-4 flex gap-1 overflow-x-auto px-4 md:mx-0 md:flex-col md:overflow-visible md:px-0">
          {sections.map((s) => (
            <button
              key={s.key}
              onClick={() => setParams({ s: s.key })}
              className={cn(
                "flex shrink-0 items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm transition-colors",
                current === s.key ? "bg-surface font-medium text-text shadow-soft ring-1 ring-border" : "text-text-2 hover:bg-surface-3 hover:text-text",
              )}
            >
              <s.icon className={cn("size-4 shrink-0", current === s.key ? "text-accent" : "text-text-3")} />
              {s.label}
            </button>
          ))}
        </nav>
        <div className="min-w-0 animate-fade-in" key={current}>
          <div className="mb-5">
            <h2 className="text-lg font-semibold text-text">{sec.label}</h2>
            <p className="text-[13px] text-text-3">{sec.desc}</p>
          </div>
          {current === "language" && <LanguageSection />}
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
