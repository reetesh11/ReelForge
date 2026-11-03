import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "./client";
import type { components } from "./schema";

export type VoiceOut = components["schemas"]["VoiceOut"];
export type VoiceModelState = components["schemas"]["VoiceModelOut"];
export type Job = components["schemas"]["JobOut"];

export type LineState =
  | "no_dialogue"
  | "no_voice"
  | "no_take"
  | "queued"
  | "rendering"
  | "ready"
  | "approved"
  | "stale"
  | "failed";

export interface VoiceTake {
  id: string;
  take_no: number;
  seed: number;
  duration_s: number | null;
  active: boolean;
  approved: boolean;
  stale: boolean;
  audio_url: string;
}

export interface VoiceLine {
  scene_id: string;
  position: number;
  speaker: string | null;
  speaker_name?: string;
  text: string;
  language: string;
  state: LineState;
  message?: string;
  speed: number;
  pause_before: number;
  pause_after: number;
  takes: VoiceTake[];
  duration_s?: number;
  frames?: number;
  shot_length_s?: number;
  shot_length_stale: boolean;
  over_budget?: { line_s: number; budget_s: number };
}

export interface VoiceBoardState {
  stage: string;
  voice_model: { key: string; label: string; model_id: string };
  presets: Array<{ id: string; label: string }>;
  approved_count: number;
  total: number;
  stale_count: number;
  characters: Array<{ key: string; name: string; avatar_url?: string | null; voice: VoiceOut | null }>;
  lines: VoiceLine[];
  job: Job | null;
}

export interface LineAction {
  project_stage: string;
  approved_count: number;
  total: number;
  line: VoiceLine;
  message?: string | null;
}

export type TimingBody = { speed?: number; pause_before?: number; pause_after?: number };

/** The voice API is not available for this project (older backend, or the cast is not approved). */
export class VoicesUnavailableError extends Error {}

function detailFrom(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : fallback;
}

async function detailOf(response: Response, fallback: string): Promise<string> {
  const body = (await response.clone().json().catch(() => ({}))) as { detail?: unknown };
  return typeof body.detail === "string" ? body.detail : fallback;
}

export function useVoices(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.voices(projectId),
    enabled,
    retry: (count, error) => !(error instanceof VoicesUnavailableError) && count < 2,
    refetchInterval: (query) => {
      const status = query.state.data?.job?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    },
    queryFn: async (): Promise<VoiceBoardState> => {
      const { data, response } = await api.GET("/api/v1/projects/{project_id}/voices", {
        params: { path: { project_id: projectId } },
      });
      if (response.status === 404 || response.status === 409) {
        throw new VoicesUnavailableError("voices are not available");
      }
      if (!data) throw new Error("could not load the voices");
      return data as unknown as VoiceBoardState;
    },
  });
}

function useRefresh(projectId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.voices(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.stages(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.library });
  };
}

export function useVoiceModel() {
  return useQuery({
    queryKey: queryKeys.voiceModel,
    queryFn: async (): Promise<VoiceModelState | null> => {
      const { data } = await api.GET("/api/v1/voice-model");
      return data && Array.isArray(data.choices) ? data : null;
    },
  });
}

export function useSetVoiceModel() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (voiceModel: string): Promise<void> => {
      const { error, response } = await api.PUT("/api/v1/voice-model", {
        body: { voice_model: voiceModel },
      });
      if (!response.ok) throw new Error(detailFrom(error, "could not change the voice model"));
    },
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

export type SetVoiceBody = components["schemas"]["VoiceSetRequest"];

export function useSetVoice(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async ({ key, body }: { key: string; body: SetVoiceBody }): Promise<VoiceOut> => {
      const { data, error } = await api.POST("/api/v1/projects/{project_id}/voices/characters/{key}:set", {
        params: { path: { project_id: projectId, key } },
        body,
      });
      if (!data) throw new Error(detailFrom(error, "could not set the voice"));
      return data;
    },
    onSuccess: refresh,
  });
}

export function useClearVoice(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async (key: string): Promise<void> => {
      const { error, response } = await api.POST(
        "/api/v1/projects/{project_id}/voices/characters/{key}:clear",
        { params: { path: { project_id: projectId, key } } },
      );
      if (!response.ok) throw new Error(detailFrom(error, "could not clear the voice"));
    },
    onSuccess: refresh,
  });
}

export function useUploadReference(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async ({ key, file, text }: { key: string; file: File; text?: string }): Promise<VoiceOut> => {
      const form = new FormData();
      form.append("file", file);
      if (text !== undefined) form.append("reference_text", text);
      const res = await globalThis.fetch(`/api/v1/projects/${projectId}/voices/characters/${key}:upload-reference`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(await detailOf(res, "could not upload that clip"));
      return (await res.json()) as VoiceOut;
    },
    onSuccess: refresh,
  });
}

export type GenerateMode = "missing" | "stale" | "lines";

export function useGenerateVoices(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async ({ mode, lines }: { mode: GenerateMode; lines?: string[] }): Promise<Job> => {
      const { data, error } = await api.POST("/api/v1/projects/{project_id}/voices:generate", {
        params: { path: { project_id: projectId } },
        body: { mode, lines },
      });
      if (!data) throw new Error(detailFrom(error, "could not start generating"));
      return data;
    },
    onSuccess: refresh,
  });
}

export function useCancelVoiceJob(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async (jobId: string): Promise<void> => {
      const { error, response } = await api.POST("/api/v1/jobs/{job_id}/cancel", {
        params: { path: { job_id: jobId } },
      });
      if (!response.ok) throw new Error(detailFrom(error, "could not cancel"));
    },
    onSuccess: refresh,
  });
}

export type LineActionName =
  | "approve"
  | "select-take"
  | "edit-text"
  | "set-timing"
  | "speed-up"
  | "extend-scene";

export function useLineAction(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async ({
      sceneId,
      name,
      body,
    }: {
      sceneId: string;
      name: LineActionName;
      body?: Record<string, unknown>;
    }): Promise<LineAction> => {
      const res = await globalThis.fetch(`/api/v1/projects/${projectId}/voices/lines/${sceneId}:${name}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      });
      if (!res.ok) throw new Error(await detailOf(res, "that didn't work"));
      return (await res.json()) as LineAction;
    },
    onSuccess: refresh,
  });
}

export function useUploadRecording(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: async ({ sceneId, file }: { sceneId: string; file: File }): Promise<void> => {
      const form = new FormData();
      form.append("file", file);
      const res = await globalThis.fetch(
        `/api/v1/projects/${projectId}/voices/lines/${sceneId}:upload-recording`,
        { method: "POST", body: form },
      );
      if (!res.ok) throw new Error(await detailOf(res, "could not upload that recording"));
    },
    onSuccess: refresh,
  });
}

export function useShorten(projectId: string) {
  return useMutation({
    mutationFn: async (sceneId: string): Promise<string> => {
      const res = await globalThis.fetch(`/api/v1/projects/${projectId}/voices/lines/${sceneId}:shorten`, {
        method: "POST",
      });
      if (!res.ok) throw new Error(await detailOf(res, "could not shorten this line"));
      return ((await res.json()) as { proposal: string }).proposal;
    },
  });
}

/** Start a preset preview job and resolve with the audio URL once it has finished. */
export function usePresetPreview(projectId: string) {
  return useMutation({
    mutationFn: async (presetId: string): Promise<string> => {
      const { data, error } = await api.POST("/api/v1/projects/{project_id}/voices/presets/{preset_id}:preview", {
        params: { path: { project_id: projectId, preset_id: presetId } },
      });
      if (!data) throw new Error(detailFrom(error, "could not preview this voice"));
      for (let i = 0; i < 120; i += 1) {
        const { data: job } = await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: data.id } } });
        if (job?.status === "succeeded") {
          const url = (job.result as { audio_url?: string } | null)?.audio_url;
          if (url) return url;
          break;
        }
        if (job && (job.status === "failed" || job.status === "cancelled")) {
          throw new Error(job.error ?? "could not preview this voice");
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      throw new Error("could not preview this voice");
    },
  });
}

export function previewUrl(projectId: string, sceneId?: string): string {
  const base = `/api/v1/projects/${projectId}/voices/preview`;
  return sceneId ? `${base}?scene_id=${encodeURIComponent(sceneId)}` : base;
}
