export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "partial" | "interrupted";

export interface Job {
  id: string;
  kind?: string;
  paper_id?: string | null;
  status: JobStatus;
  progress: number;
  total: number;
  message: string | null;
  error: string | null;
  error_code: string | null;
  result?: any;
  created_at?: string;
  updated_at?: string;
}

export interface Settings {
  daily_count: number;
  window_days: number;
  time_preference: "latest" | "balanced" | "relaxed";
  ranking_preset: "balanced" | "relevance" | "quality" | "fresh" | "custom";
  weights: { relevance: number; quality: number; freshness: number };
  sources: Record<string, boolean>;
  signals: Record<string, boolean>;
  ai_rerank: boolean;
  auto_fetch_on_open: boolean;
  ai: {
    base_url: string;
    model: string;
    thinking_for_analysis: boolean;
    features: { translate: boolean; summary: boolean; modules: boolean; contributions: boolean };
    translate_appendix: boolean;
    keep_english_terms: boolean;
    concurrency: number;
  };
  reading: { theme: "system" | "light" | "dark"; font_size: "sm" | "md" | "lg"; translation_view: "bilingual" | "zh" | "en" };
  onboarded: boolean;
}

export interface Direction {
  id: number;
  name: string;
  keywords: string[];
  exclude: string[];
  categories: string[];
  weight: number;
  enabled: boolean;
  sort_order: number;
}

export interface DirectionPreset {
  key: string;
  name: string;
  name_en: string;
  keywords: string[];
  categories: string[];
}

export interface Meta {
  direction_presets: DirectionPreset[];
  arxiv_categories: { id: string; name: string }[];
  ranking_presets: Record<string, { relevance: number; quality: number; freshness: number }>;
  time_preferences: Record<string, number>;
  default_models: string[];
}

export interface PaperState {
  read: boolean;
  read_at: string | null;
  starred: boolean;
  dismissed: boolean;
  opened_at: string | null;
  note: string | null;
}

export interface PaperCard {
  id: string;
  title: string;
  authors: string[];
  author_count: number;
  abstract: string | null;
  published: string | null;
  date_quality: string | null;
  venue: string | null;
  arxiv_id: string | null;
  doi: string | null;
  url: string | null;
  pdf_url: string | null;
  categories: string[];
  sources: string[];
  state: PaperState;
}

export interface Paper extends Omit<PaperCard, "state" | "sources" | "author_count"> {
  date_note: string | null;
  updated: string | null;
  openalex_id: string | null;
  s2_id: string | null;
  pmid: string | null;
  html_url: string | null;
  comment: string | null;
  journal_ref: string | null;
  sources: { source: string; id: string; url: string | null }[];
  signals: Record<string, any>;
}

export interface QualitySignal {
  key: string;
  label: string;
  score: number;
  evidence?: string;
}

export interface Breakdown {
  total: number;
  relevance: number;
  keyword_relevance: number;
  ai_relevance: number | null;
  quality: number;
  quality_confidence: number;
  quality_insufficient: boolean;
  quality_signals: QualitySignal[];
  freshness: number;
  weights: { relevance: number; quality: number; freshness: number };
  matched: { title: string[]; abstract: string[]; category: string | null };
}

export interface RecAI {
  relevance: number;
  reason: string;
  title_zh: string;
  tldr: string;
}

export interface AiStatusSummary {
  summary?: boolean;
  modules?: boolean;
  contributions?: boolean;
  abstract_translation?: boolean;
  translation_units?: number;
}

export interface RecItem {
  rec_id: number;
  batch_id: number;
  rank: number;
  score: number;
  breakdown: Breakdown;
  reasons: string[];
  direction_name: string;
  ai: RecAI | null;
  recommended_at: string;
  paper: PaperCard;
  ai_status: AiStatusSummary;
}

export interface SourceStat {
  name: string;
  fetched: number;
  errors: string[];
}

export interface Batch {
  id: number;
  created_at: string;
  day: string;
  params: {
    mode: string;
    count: number;
    window_days: number;
    sources: string[];
    directions: { id: number; name: string }[];
    ai_rerank: boolean;
  };
  stats: {
    sources: Record<string, SourceStat>;
    merged?: number;
    in_window?: number;
    already_seen?: number;
    relevant?: number;
    ai_rerank?: { used: boolean; note?: string };
    hf_daily?: { matched: number; error: string | null };
  };
  message: string | null;
}

export interface TodayResponse {
  day: string;
  batches: Batch[];
  items: RecItem[];
  last_batch: Batch | null;
  active_job: Job | null;
}

export interface HistoryDay {
  day: string;
  batches: Batch[];
  items: RecItem[];
}

export type AiKind = "summary" | "modules" | "contributions" | "abstract_translation";

export interface AiResult<T = any> {
  kind: string;
  content: T;
  basis: { type: "fulltext" | "abstract"; source_label?: string; reason?: string; truncated?: boolean; thinking?: boolean } | null;
  model: string;
  usage: { prompt_tokens?: number; completion_tokens?: number; cache_hit_tokens?: number };
  created_at: string;
}

export type FeatureStatus = "idle" | "running" | "done" | "failed" | "partial" | "disabled";

export interface FeatureState<T = any> {
  status: FeatureStatus;
  job: Job | null;
  result?: AiResult<T> | null;
  enabled: boolean;
  upgradable?: boolean;
  progress?: { total: number; done: number; sections: Record<string, { total: number; done: number }> };
}

export interface FulltextInfo {
  available: boolean;
  source: string;
  source_label: string;
  source_url: string;
  fetched_at: string;
  stats: { sections: number; words: number; figures: number; tables: number; equations: number };
  warnings: string[];
}

export interface PaperDetail {
  paper: Paper;
  state: PaperState;
  recommendation: {
    score: number;
    breakdown: Breakdown;
    reasons: string[];
    direction_name: string;
    ai: RecAI | null;
    recommended_at: string;
    batch_id: number;
  } | null;
  fulltext: FulltextInfo | null;
  fulltext_job: Job | null;
  ai: {
    summary: FeatureState;
    modules: FeatureState;
    contributions: FeatureState;
    abstract_translation: FeatureState<{ title_zh: string; abstract_zh: string }>;
    translate: FeatureState;
  };
  ai_configured: boolean;
}

// ---------- full-text document ----------
export interface TableCell {
  t: string;
  cs?: number;
  rs?: number;
  h?: boolean;
  b?: boolean;
}

export type Block =
  | { id: string; type: "paragraph" | "heading"; text: string }
  | { id: string; type: "equation"; latex: string; tag: string | null }
  | { id: string; type: "list"; ordered: boolean; items: string[] }
  | { id: string; type: "figure"; label: string | null; caption: string; images: string[]; subcaptions: string[] }
  | { id: string; type: "table"; label: string | null; caption: string; tables: TableCell[][][]; text?: string }
  | { id: string; type: "code"; label: string | null; caption: string; text: string }
  | { id: string; type: "reference"; label: string | null; text: string }
  | { id: string; type: "unparsed"; text: string; note: string };

export interface Section {
  id: string;
  level: number;
  number: string | null;
  title: string;
  kind: "abstract" | "front" | "body" | "appendix" | "references";
  blocks: Block[];
}

export interface FullDoc {
  version: number;
  source: "arxiv_html" | "pdf";
  source_label: string;
  source_url: string;
  title: string;
  warnings: string[];
  sections: Section[];
  stats: { sections: number; words: number; figures: number; tables: number; equations: number };
  fetched_at?: string;
}

export interface FulltextResponse {
  available: boolean;
  doc?: FullDoc;
  translations?: Record<string, { text: string; flags: string[] }>;
  translation_status?: { total: number; done: number; sections: Record<string, { total: number; done: number }> };
  glossary?: { en: string; zh: string; keep: boolean }[];
  job?: Job | null;
}

export interface SourceInfo {
  id: string;
  name: string;
  description: string;
  homepage: string;
  key_policy: "none" | "optional" | "recommended";
  key_help: string;
  coverage: string;
  enabled: boolean;
  key_configured: boolean;
  key_masked: string | null;
  last?: { fetched: number; errors: string[]; at: string } | null;
}

export interface SourcesResponse {
  sources: SourceInfo[];
  signals: { id: string; name: string; enabled: boolean; description: string }[];
}

export type AiProvider = "deepseek" | "gemini";

export interface ProviderConfig {
  configured: boolean;
  key_masked: string | null;
  label: string;
  base_url: string;
  model: string;
  models: string[];
  last_test: { ok: boolean; at: string; error?: string; steps?: TestStep[] } | null;
  // Gemini only
  proxy?: string;
  free_tier?: boolean;
  rpm?: number;
  requests_today?: Record<string, number>;
  reset_hour_beijing?: number;
}

export interface AiConfig {
  provider: AiProvider;
  providers: Record<AiProvider, ProviderConfig>;
  label: string;
  configured: boolean;
  key_masked: string | null;
  base_url: string;
  model: string;
  models: string[];
  thinking_for_analysis: boolean;
  secret_backend: string;
  last_test: ProviderConfig["last_test"];
}

export interface TestStep {
  name: string;
  ok: boolean;
  detail: string;
}

export interface TestResult {
  at?: string;
  provider?: AiProvider;
  message?: string;
  ok: boolean;
  steps: TestStep[];
  error?: string;
  error_code?: string;
  models?: string[];
  balance?: { available: boolean; infos: { currency: string; total_balance: string }[] };
}

export interface UsageAgg {
  calls: number;
  prompt: number;
  completion: number;
  cache_hit: number;
}

export interface Usage {
  today: UsageAgg;
  last_30_days: UsageAgg;
  total: UsageAgg;
  by_kind_30d: { kind: string; calls: number; prompt: number; completion: number }[];
}

export interface SystemStatus {
  app: string;
  version: string;
  data_dir: string;
  db_size: number;
  counts: Record<string, number>;
  ai_configured: boolean;
  secret_backend: string;
  python: string;
  uptime_seconds: number;
  active_jobs: number;
}

export interface UpdateInfo {
  current: string;
  latest: string | null;
  has_update: boolean;
  url: string;
  published_at?: string | null;
  notes?: string;
}

export interface LibraryItem {
  paper: PaperCard;
  ai_status: AiStatusSummary;
  recommendation: { score: number; direction_name: string; recommended_at: string; ai: RecAI | null } | null;
}
