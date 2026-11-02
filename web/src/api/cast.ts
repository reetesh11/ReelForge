import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "./client";
import type { components } from "./schema";

export type CastState = components["schemas"]["CastOut"];
export type CastItem = components["schemas"]["CastItemOut"];
export type CastCandidate = components["schemas"]["CastCandidateOut"];
export type CastAction = components["schemas"]["CastActionOut"];
export type CastBackend = components["schemas"]["CastBackendOut"];
export type GenerateBody = Partial<components["schemas"]["CastGenerateRequest"]>;
export type Job = components["schemas"]["JobOut"];

/** The server has no cast API for this project yet (older backend, or the story is not approved). */
export class CastUnavailableError extends Error {}

async function detailOf(response: Response, fallback: string): Promise<string> {
  const body = (await response
    .clone()
    .json()
    .catch(() => ({}))) as { detail?: unknown };
  return typeof body.detail === "string" ? body.detail : fallback;
}

export function useCast(projectId: string) {
  return useQuery({
    queryKey: queryKeys.cast(projectId),
    retry: (count, error) => !(error instanceof CastUnavailableError) && count < 2,
    queryFn: async (): Promise<CastState> => {
      const { data, response } = await api.GET("/api/v1/projects/{project_id}/cast", {
        params: { path: { project_id: projectId } },
      });
      if (response.status === 404 || response.status === 409) {
        throw new CastUnavailableError("cast stage is not available");
      }
      if (!data) throw new Error("could not load the cast");
      return data;
    },
  });
}

function detailFrom(error: unknown, fallback: string): string {
  const detail = (error as { detail?: unknown } | undefined)?.detail;
  return typeof detail === "string" ? detail : fallback;
}

function useRefreshCast(projectId: string) {
  const queryClient = useQueryClient();
  return async () => {
    await queryClient.invalidateQueries({ queryKey: queryKeys.cast(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.stages(projectId) });
  };
}

export function useGenerate(projectId: string) {
  const refresh = useRefreshCast(projectId);
  return useMutation({
    mutationFn: async ({ key, body }: { key: string; body: GenerateBody }): Promise<Job> => {
      const { data, error } = await api.POST("/api/v1/projects/{project_id}/cast/{key}:generate", {
        params: { path: { project_id: projectId, key } },
        body: { regenerate: false, ...body },
      });
      if (!data) throw new Error(detailFrom(error, "could not start generating"));
      return data;
    },
    onSuccess: refresh,
  });
}

export function useApproveCandidate(projectId: string) {
  const refresh = useRefreshCast(projectId);
  return useMutation({
    mutationFn: async ({ key, candidateId }: { key: string; candidateId: string }): Promise<void> => {
      const { error, response } = await api.POST("/api/v1/projects/{project_id}/cast/{key}:approve", {
        params: { path: { project_id: projectId, key } },
        body: { candidate_id: candidateId },
      });
      if (!response.ok) throw new Error(detailFrom(error, "could not approve this image"));
    },
    onSuccess: refresh,
  });
}

export function useReopen(projectId: string) {
  const refresh = useRefreshCast(projectId);
  return useMutation({
    mutationFn: async (key: string): Promise<void> => {
      const { error, response } = await api.POST("/api/v1/projects/{project_id}/cast/{key}:reopen", {
        params: { path: { project_id: projectId, key } },
      });
      if (!response.ok) throw new Error(detailFrom(error, "could not change the approval"));
    },
    onSuccess: refresh,
  });
}

export function useUseLibrary(projectId: string) {
  const refresh = useRefreshCast(projectId);
  return useMutation({
    mutationFn: async ({ key, characterId }: { key: string; characterId: string }): Promise<void> => {
      const { error, response } = await api.POST("/api/v1/projects/{project_id}/cast/{key}:use-library", {
        params: { path: { project_id: projectId, key } },
        body: { character_id: characterId },
      });
      if (!response.ok) throw new Error(detailFrom(error, "could not use that library character"));
    },
    onSuccess: refresh,
  });
}

export function useUpload(projectId: string) {
  const refresh = useRefreshCast(projectId);
  return useMutation({
    mutationFn: async ({ key, file }: { key: string; file: File }): Promise<void> => {
      const form = new FormData();
      form.append("file", file);
      const res = await globalThis.fetch(`/api/v1/projects/${projectId}/cast/${key}:upload`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) throw new Error(await detailOf(res, "could not upload that image"));
    },
    onSuccess: refresh,
  });
}

export function useCancelJob(projectId: string) {
  const refresh = useRefreshCast(projectId);
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
