import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "./client";
import { postFile, postJson } from "./http";
import type { components } from "./schema";

export type Job = components["schemas"]["JobOut"];

export type ShotType = "talking" | "action" | "continue";
export type Quality = "draft" | "final";
export type ShotState = "no_shot" | "queued" | "rendering" | "ready" | "approved" | "stale" | "failed";
export type Blocker = "frame_not_approved" | "voice_not_approved" | "waiting_previous";

export interface ShotTake {
  id: string;
  take_no: number;
  seed: number;
  active: boolean;
  approved: boolean;
  stale: boolean;
  source: "render" | "upload";
  quality: Quality;
  video_url: string;
  last_frame_id: string | null;
  inputs: string[];
}

export interface Shot {
  scene_id: string;
  position: number;
  shot_type: ShotType;
  shot_type_auto: ShotType;
  quality: Quality;
  width: number;
  height: number;
  frames: number;
  shot_length_s: number;
  motion_prompt: string;
  state: ShotState;
  message?: string;
  oom?: boolean;
  can_retry_draft?: boolean;
  blockers: Blocker[];
  frame_url: string | null;
  takes: ShotTake[];
  job: Job | null;
}

export interface QueueRow {
  job_id: string;
  scene_id: string;
  position: number;
  shot_type: ShotType;
  quality: Quality;
  width: number;
  height: number;
  status: "queued" | "running";
  estimate_s: number;
  estimate_text: string;
  can_move: boolean;
}

export interface Queue {
  paused: boolean;
  rows: QueueRow[];
  total_shots: number;
  total_s: number;
  total_text: string;
  running: { scene_id: string; index: number; total: number; elapsed_s: number } | null;
}

export interface ShotsState {
  stage: string;
  engine: { ok: boolean; message: string };
  approved_count: number;
  total: number;
  stale_count: number;
  shots: Shot[];
  queue: Queue;
}

export interface ShotAction {
  project_stage: string;
  approved_count: number;
  total: number;
  shot: Shot;
  job?: Job;
}

/** The shots API is not available for this project (older backend, or key frames not approved). */
export class ShotsUnavailableError extends Error {}

export function useShots(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.shots(projectId),
    enabled,
    retry: (count, error) => !(error instanceof ShotsUnavailableError) && count < 2,
    refetchInterval: (query) => {
      const data = query.state.data;
      const active = (data?.queue.rows.length ?? 0) > 0 || (data?.shots.some((s) => s.job !== null) ?? false);
      return active ? 1500 : false;
    },
    queryFn: async (): Promise<ShotsState> => {
      const { data, response } = await api.GET("/api/v1/projects/{project_id}/shots", {
        params: { path: { project_id: projectId } },
      });
      if (response.status === 404 || response.status === 409) {
        throw new ShotsUnavailableError("shots are not available");
      }
      if (!data) throw new Error("could not load the shots");
      return data as unknown as ShotsState;
    },
  });
}

function useRefresh(projectId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.shots(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.frames(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.stages(projectId) });
  };
}

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export function useRenderAll(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: (mode: "missing" | "stale") =>
      postJson<{ jobs: Job[]; skipped: Array<{ scene_id: string; reason: string }> }>(
        `${base(projectId)}/shots:render-all`,
        { mode },
        "could not start rendering",
      ),
    onSuccess: refresh,
  });
}

export type RenderName = "render" | "reroll" | "retry-draft";

export function useRenderShot(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: ({ sceneId, name }: { sceneId: string; name: RenderName }) =>
      postJson<Job>(`${base(projectId)}/shots/${sceneId}:${name}`, {}, "could not start rendering"),
    onSuccess: refresh,
  });
}

export type ShotActionName =
  | "approve"
  | "select-take"
  | "set-type"
  | "set-quality"
  | "save-prompt"
  | "dequeue";

export function useShotAction(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: ({ sceneId, name, body }: { sceneId: string; name: ShotActionName; body?: Record<string, unknown> }) =>
      postJson<ShotAction>(`${base(projectId)}/shots/${sceneId}:${name}`, body),
    onSuccess: refresh,
  });
}

export function useUploadClip(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: ({ sceneId, file }: { sceneId: string; file: File }) =>
      postFile<ShotAction>(`${base(projectId)}/shots/${sceneId}:upload-clip`, file, "could not upload that clip"),
    onSuccess: refresh,
  });
}

export type QueueActionName = "pause" | "resume" | "cancel" | "move";

export function useQueueAction(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: ({ name, body }: { name: QueueActionName; body?: Record<string, unknown> }) =>
      postJson<Queue>(`${base(projectId)}/shots/queue:${name}`, body),
    onSuccess: refresh,
  });
}
