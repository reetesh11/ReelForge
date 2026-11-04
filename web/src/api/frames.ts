import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "./client";
import { postFile, postJson } from "./http";
import type { components } from "./schema";

export type Job = components["schemas"]["JobOut"];

export type FrameState =
  | "no_frame"
  | "queued"
  | "rendering"
  | "ready"
  | "approved"
  | "stale"
  | "failed"
  | "continue_previous";

export type Framing = "wide" | "medium" | "closeup";

export interface FrameTake {
  id: string;
  take_no: number;
  seed: number;
  active: boolean;
  approved: boolean;
  stale: boolean;
  source: "render" | "upload";
  image_url: string;
  inputs: string[];
}

export interface FrameNotes {
  second_character?: { master_name: string; other_name: string };
  product?: "included" | "missing";
  waiting_for_previous_shot?: boolean;
  needs_master?: string;
  no_character?: boolean;
}

export interface Frame {
  scene_id: string;
  position: number;
  characters: Array<{ key: string; name: string }>;
  master: { key: string; name: string; artifact_id: string } | null;
  framing: Framing;
  state: FrameState;
  message?: string;
  prompt: string;
  prompt_source: "llm" | "user" | "";
  look_removed: boolean;
  takes: FrameTake[];
  notes: FrameNotes;
  continue_previous: boolean;
  job: Job | null;
}

export interface FramesState {
  stage: string;
  approved_count: number;
  total: number;
  stale_count: number;
  jobs: Job[];
  frames: Frame[];
}

export interface FrameAction {
  project_stage: string;
  approved_count: number;
  total: number;
  frame: Frame;
  job?: Job;
}

/** The frames API is not available for this project (older backend, or voices not approved). */
export class FramesUnavailableError extends Error {}

export function useFrames(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.frames(projectId),
    enabled,
    retry: (count, error) => !(error instanceof FramesUnavailableError) && count < 2,
    refetchInterval: (query) => ((query.state.data?.jobs.length ?? 0) > 0 ? 1500 : false),
    queryFn: async (): Promise<FramesState> => {
      const { data, response } = await api.GET("/api/v1/projects/{project_id}/frames", {
        params: { path: { project_id: projectId } },
      });
      if (response.status === 404 || response.status === 409) {
        throw new FramesUnavailableError("key frames are not available");
      }
      if (!data) throw new Error("could not load the key frames");
      return data as unknown as FramesState;
    },
  });
}

function useRefresh(projectId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.frames(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.shots(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.stages(projectId) });
  };
}

const base = (projectId: string) => `/api/v1/projects/${projectId}`;

export type GenerateFramesMode = "missing" | "stale" | "scenes";

export function useGenerateFrames(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: (body: { mode: GenerateFramesMode; scenes?: string[] }) =>
      postJson<{ jobs: Job[]; skipped: Array<{ scene_id: string; reason: string }> }>(
        `${base(projectId)}/frames:generate`,
        body,
        "could not start generating",
      ),
    onSuccess: refresh,
  });
}

export function useCancelFrames(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: () => postJson<{ cancelled: number }>(`${base(projectId)}/frames:cancel`, {}, "could not cancel"),
    onSuccess: refresh,
  });
}

export function useGenerateFrame(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: (sceneId: string) =>
      postJson<Job>(`${base(projectId)}/frames/${sceneId}:generate`, {}, "could not start generating"),
    onSuccess: refresh,
  });
}

export type FrameActionName = "approve" | "select-take" | "set-framing" | "save-prompt" | "continue-previous";

export function useFrameAction(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: ({ sceneId, name, body }: { sceneId: string; name: FrameActionName; body?: Record<string, unknown> }) =>
      postJson<FrameAction>(`${base(projectId)}/frames/${sceneId}:${name}`, body),
    onSuccess: refresh,
  });
}

export function useUploadFrame(projectId: string) {
  const refresh = useRefresh(projectId);
  return useMutation({
    mutationFn: ({ sceneId, file }: { sceneId: string; file: File }) =>
      postFile<FrameAction>(`${base(projectId)}/frames/${sceneId}:upload`, file, "could not upload that image"),
    onSuccess: refresh,
  });
}
