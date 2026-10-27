import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";
import type {
  AiConfig,
  AiKind,
  Direction,
  FulltextResponse,
  HistoryDay,
  Job,
  LibraryItem,
  Meta,
  PaperDetail,
  PaperState,
  Settings,
  SourcesResponse,
  SystemStatus,
  TodayResponse,
  Usage,
} from "./types";

export const isActive = (j?: Job | null) => !!j && (j.status === "queued" || j.status === "running");

export function useSettings() {
  return useQuery({ queryKey: ["settings"], queryFn: () => api.get<Settings>("/settings"), staleTime: 60_000 });
}

export function useUpdateSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (patch: Partial<Settings> | Record<string, unknown>) => api.patch<Settings>("/settings", patch),
    onMutate: async (patch) => {
      await qc.cancelQueries({ queryKey: ["settings"] });
      const prev = qc.getQueryData<Settings>(["settings"]);
      if (prev) qc.setQueryData(["settings"], deepMerge(prev, patch));
      return { prev };
    },
    onError: (_e, _p, ctx) => ctx?.prev && qc.setQueryData(["settings"], ctx.prev),
    onSuccess: (data) => qc.setQueryData(["settings"], data),
  });
}

function deepMerge<T>(base: T, patch: any): T {
  const out: any = Array.isArray(base) ? [...(base as any)] : { ...(base as any) };
  for (const [k, v] of Object.entries(patch ?? {})) {
    out[k] = v && typeof v === "object" && !Array.isArray(v) && out[k] && typeof out[k] === "object" ? deepMerge(out[k], v) : v;
  }
  return out;
}

export function useMeta() {
  return useQuery({ queryKey: ["meta"], queryFn: () => api.get<Meta>("/meta"), staleTime: Infinity });
}

export function useDirections() {
  return useQuery({ queryKey: ["directions"], queryFn: () => api.get<Direction[]>("/directions") });
}

export function useDirectionMutations() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["directions"] });
  return {
    create: useMutation({ mutationFn: (d: Partial<Direction>) => api.post<Direction>("/directions", d), onSuccess: done }),
    update: useMutation({
      mutationFn: ({ id, ...d }: Partial<Direction> & { id: number }) => api.patch<Direction>(`/directions/${id}`, d),
      onSuccess: done,
    }),
    remove: useMutation({ mutationFn: (id: number) => api.del(`/directions/${id}`), onSuccess: done }),
    addPresets: useMutation({
      mutationFn: (keys: string[]) => api.post<Direction[]>("/directions/presets", { keys }),
      onSuccess: () => {
        done();
        qc.invalidateQueries({ queryKey: ["settings"] });
      },
    }),
  };
}

export function useToday() {
  return useQuery({
    queryKey: ["today"],
    queryFn: () => api.get<TodayResponse>("/recommend/today"),
    refetchInterval: (q) => (isActive(q.state.data?.active_job) ? 2000 : false),
  });
}

export function useHistory() {
  return useQuery({ queryKey: ["history"], queryFn: () => api.get<HistoryDay[]>("/recommend/history?days=60") });
}

export function useJob(id: string | null | undefined, onFinish?: (j: Job) => void) {
  return useQuery({
    queryKey: ["job", id],
    enabled: !!id,
    queryFn: async () => {
      const j = await api.get<Job>(`/jobs/${id}`);
      if (!isActive(j)) onFinish?.(j);
      return j;
    },
    refetchInterval: (q) => (q.state.data && !isActive(q.state.data) ? false : 900),
  });
}

export function usePaper(id: string | undefined) {
  return useQuery({
    queryKey: ["paper", id],
    enabled: !!id,
    queryFn: () => api.get<PaperDetail>(`/papers/${id}`),
    refetchInterval: (q) => {
      const d = q.state.data;
      if (!d) return false;
      const anyRunning = Object.values(d.ai).some((f) => f.status === "running") || isActive(d.fulltext_job);
      return anyRunning ? 1200 : false;
    },
  });
}

export function useFulltext(id: string | undefined, poll: boolean) {
  return useQuery({
    queryKey: ["fulltext", id],
    enabled: !!id,
    queryFn: () => api.get<FulltextResponse>(`/papers/${id}/fulltext`),
    refetchInterval: poll ? 1500 : false,
  });
}

export function usePaperState(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (s: Partial<PaperState> & { opened?: boolean }) => api.patch<PaperState>(`/papers/${id}/state`, s),
    onSuccess: (state) => {
      qc.setQueryData<PaperDetail | undefined>(["paper", id], (d) => (d ? { ...d, state } : d));
      qc.invalidateQueries({ queryKey: ["today"] });
      qc.invalidateQueries({ queryKey: ["library"] });
      qc.invalidateQueries({ queryKey: ["history"] });
    },
  });
}

export function useRunAi(paperId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ kind, force }: { kind: AiKind; force?: boolean }) =>
      api.post<Job | { status: "cached" }>(`/papers/${paperId}/ai/${kind}`, { force: !!force }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["paper", paperId] }),
  });
}

export function useLibrary(filter: string, q: string, limit = 30) {
  return useQuery({
    queryKey: ["library", filter, q, limit],
    queryFn: () =>
      api.get<{ items: LibraryItem[]; total: number }>(
        `/papers?filter=${encodeURIComponent(filter)}&q=${encodeURIComponent(q)}&limit=${limit}`,
      ),
    placeholderData: (prev) => prev,
  });
}

export function useSources() {
  return useQuery({ queryKey: ["sources"], queryFn: () => api.get<SourcesResponse>("/sources") });
}

export function useAiConfig() {
  return useQuery({ queryKey: ["ai-config"], queryFn: () => api.get<AiConfig>("/ai/config") });
}

export function useUsage() {
  return useQuery({ queryKey: ["usage"], queryFn: () => api.get<Usage>("/usage") });
}

export function useStatus() {
  return useQuery({ queryKey: ["status"], queryFn: () => api.get<SystemStatus>("/status") });
}
