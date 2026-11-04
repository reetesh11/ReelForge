import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "./client";
import { detailOf, postJson } from "./http";
import type { Job } from "./shots";

export interface EdlShot {
  scene_id: string;
  artifact: string;
  source_duration_s: number;
  in_s: number;
  out_s: number;
  transition_in_s: number;
}

export interface EdlDialogue {
  scene_id: string;
  artifact: string;
  offset_s: number;
  duration_s: number;
  gain_db: number;
}

export interface EdlCaption {
  scene_id: string;
  speaker: string | null;
  line_no: number;
  text: string;
  start_s: number;
  end_s: number;
  style: string | null;
}

export interface Edl {
  version: number;
  fps: number;
  width: number;
  height: number;
  project_id: string;
  video: EdlShot[];
  dialogue: EdlDialogue[];
  captions: EdlCaption[];
  caption_style: string;
}

export interface AssemblyTake {
  id: string;
  take_no: number;
  active: boolean;
  video_url: string;
}

export type PreviewState = "none" | "up_to_date" | "out_of_date" | "pending" | "rebuilding" | "failed";

export interface Preview {
  state: PreviewState;
  step: string | null;
  progress: number | null;
  url: string | null;
  job_id: string | null;
  error: string | null;
  rebuild_in_s: number | null;
}

export interface ExportInfo {
  state: "idle" | "running" | "failed";
  step: string | null;
  step_index: number | null;
  step_total: number | null;
  progress: number | null;
  job_id: string | null;
  failed_step: string | null;
  error: string | null;
}

export interface ReelVersion {
  version: number;
  label: string;
  reel_url: string;
  cover_url: string;
  created_at: string;
  missing: boolean;
}

export interface LicenceWarning {
  model: string;
  version: string;
  licence: string;
}

export interface AssemblyState {
  stage: string;
  blocked_reason: string | null;
  edl: Edl | null;
  edl_hash: string | null;
  shots: Array<{ scene_id: string; takes: AssemblyTake[] }>;
  caption_status: Record<string, "words" | "line" | "pending">;
  preview: Preview;
  export: ExportInfo;
  versions: ReelVersion[];
  licence_warnings: LicenceWarning[];
  caption_presets: Array<{ id: string; label: string }>;
}

export type EditOp = { op: string } & Record<string, unknown>;

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export function useAssembly(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.assembly(projectId),
    enabled,
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return false;
      const busy =
        data.preview.state === "pending" || data.preview.state === "rebuilding" || data.export.state === "running";
      return busy ? 1000 : false;
    },
    queryFn: async (): Promise<AssemblyState> => {
      const res = await globalThis.fetch(`${base(projectId)}/assembly`);
      if (!res.ok) throw new Error(await detailOf(res, "could not load the assembly"));
      return (await res.json()) as AssemblyState;
    },
  });
}

function useStore(projectId: string) {
  const queryClient = useQueryClient();
  return {
    set: (state: AssemblyState) => queryClient.setQueryData(queryKeys.assembly(projectId), state),
    refresh: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.assembly(projectId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.stages(projectId) });
    },
  };
}

export function useBuildAssembly(projectId: string) {
  const store = useStore(projectId);
  return useMutation({
    mutationFn: (force: boolean) =>
      postJson<AssemblyState>(`${base(projectId)}/assembly:build`, { force }, "could not build the edit"),
    onSuccess: store.set,
  });
}

export function useAssemblyEdit(projectId: string) {
  const store = useStore(projectId);
  return useMutation({
    mutationFn: (op: EditOp) =>
      postJson<{ assembly: AssemblyState; notes: string[] }>(`${base(projectId)}/assembly:edit`, op, "that edit didn't work"),
    onSuccess: (out) => store.set(out.assembly),
  });
}

export function useRebuildPreview(projectId: string) {
  const store = useStore(projectId);
  return useMutation({
    mutationFn: () => postJson<Job>(`${base(projectId)}/assembly:preview`, {}, "could not rebuild the preview"),
    onSuccess: store.refresh,
  });
}

export function useExport(projectId: string) {
  const store = useStore(projectId);
  return useMutation({
    mutationFn: (accept: boolean) =>
      postJson<Job>(`${base(projectId)}/assembly:export`, { accept_licence_warning: accept }, "could not start the export"),
    onSuccess: store.refresh,
  });
}

export function useOpenVersion(projectId: string) {
  const store = useStore(projectId);
  return useMutation({
    mutationFn: (version: number) =>
      postJson<AssemblyState>(`${base(projectId)}/assembly:open-version`, { version }, "could not open that version"),
    onSuccess: store.set,
  });
}
