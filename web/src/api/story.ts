import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "./client";
import type { components } from "./schema";

export type StoryDetail = components["schemas"]["StoryVersionDetail"];
export type StoryVersion = components["schemas"]["StoryVersionSummary"];
export type StoryVersionOut = components["schemas"]["StoryVersionOut"];
export type Affected = components["schemas"]["AffectedItem"];
export type StructureBody = components["schemas"]["StructureRequest"];
export type StaleItem = components["schemas"]["StaleItem"];
export type Job = components["schemas"]["JobOut"];

export type StoryErrorItem = { path: string; message: string; line: number | null; column: number | null };
export type Question = { path: string; question: string };
export type StructureResult = {
  version: StoryVersionOut | null;
  questions: Question[];
  draftYaml: string | null;
};

export class StoryInvalidError extends Error {
  errors: StoryErrorItem[];
  constructor(errors: StoryErrorItem[]) {
    super("story.yaml is invalid");
    this.errors = errors;
  }
}

/** The server has no story API (older backend): the stage is not available yet. */
export class StoryUnavailableError extends Error {}

export function formatStoryError(e: StoryErrorItem): string {
  const where = e.line !== null ? ` (line ${e.line})` : "";
  return `${e.path ? `${e.path}: ` : ""}${e.message}${where}`;
}

/** Read `job.result` of a finished story.structure job. */
export function parseStructureResult(result: Job["result"]): StructureResult | null {
  if (!result) return null;
  const questionsRaw = Array.isArray(result["questions"]) ? (result["questions"] as unknown[]) : [];
  const questions = questionsRaw.filter(
    (q): q is Question =>
      typeof q === "object" && q !== null && typeof (q as Question).path === "string" && typeof (q as Question).question === "string",
  );
  const version = (result["version"] ?? null) as StoryVersionOut | null;
  const draft = result["draft_yaml"];
  return { version, questions, draftYaml: typeof draft === "string" ? draft : null };
}

async function sendText(url: string, method: "PUT" | "POST", text: string): Promise<StoryVersionOut> {
  const res = await globalThis.fetch(url, { method, body: text, headers: { "Content-Type": "text/plain" } });
  if (res.status === 422) {
    const body = (await res.json()) as { errors?: StoryErrorItem[]; detail?: string };
    throw new StoryInvalidError(body.errors ?? [{ path: "", message: body.detail ?? "invalid", line: null, column: null }]);
  }
  if (!res.ok) {
    const body = (await res.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? "could not save the story");
  }
  return (await res.json()) as StoryVersionOut;
}

function useInvalidateStory(projectId: string) {
  const queryClient = useQueryClient();
  return () =>
    Promise.all([
      queryClient.invalidateQueries({ queryKey: queryKeys.story(projectId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
      queryClient.invalidateQueries({ queryKey: queryKeys.stale(projectId) }),
    ]);
}

/** The current story, or null while the project has none (404). */
export function useStory(projectId: string) {
  return useQuery({
    queryKey: queryKeys.story(projectId),
    queryFn: async (): Promise<StoryDetail | null> => {
      const { data, error, response } = await api.GET("/api/v1/projects/{project_id}/story", {
        params: { path: { project_id: projectId } },
      });
      if (response.status === 404) {
        const detail = (error as { detail?: unknown } | undefined)?.detail;
        if (detail === "no story yet") return null;
        throw new StoryUnavailableError("story stage is not available");
      }
      if (!data) throw new Error("could not load the story");
      return data;
    },
  });
}

export function useStoryVersions(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.storyVersions(projectId),
    enabled,
    queryFn: async (): Promise<StoryVersion[]> => {
      const { data } = await api.GET("/api/v1/projects/{project_id}/story/versions", {
        params: { path: { project_id: projectId } },
      });
      if (!data) throw new Error("could not load versions");
      return data;
    },
  });
}

export function useStoryVersion(projectId: string, version: number | null) {
  return useQuery({
    queryKey: queryKeys.storyVersion(projectId, version ?? 0),
    enabled: version !== null,
    queryFn: async (): Promise<StoryDetail> => {
      const { data } = await api.GET("/api/v1/projects/{project_id}/story/versions/{number}", {
        params: { path: { project_id: projectId, number: version ?? 0 } },
      });
      if (!data) throw new Error("could not load that version");
      return data;
    },
  });
}

export function useStorySchema() {
  return useQuery({
    queryKey: queryKeys.storySchema,
    staleTime: Infinity,
    queryFn: async (): Promise<Record<string, unknown>> => {
      const { data } = await api.GET("/api/v1/story/schema");
      if (!data) throw new Error("could not load the story schema");
      return data as Record<string, unknown>;
    },
  });
}

/** Stale items never throw: the editor works without them. */
export function useStale(projectId: string, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.stale(projectId),
    enabled,
    queryFn: async (): Promise<StaleItem[]> => {
      const { data } = await api.GET("/api/v1/projects/{project_id}/stale", {
        params: { path: { project_id: projectId } },
      });
      return data?.items ?? [];
    },
  });
}

export function useSaveStory(projectId: string) {
  const invalidate = useInvalidateStory(projectId);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => sendText(`/api/v1/projects/${projectId}/story`, "PUT", text),
    onSuccess: async () => {
      await invalidate();
      await queryClient.invalidateQueries({ queryKey: queryKeys.storyVersions(projectId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.stages(projectId) });
    },
  });
}

export function useImportStory(projectId: string) {
  const invalidate = useInvalidateStory(projectId);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (text: string) => sendText(`/api/v1/projects/${projectId}/story:import`, "POST", text),
    onSuccess: async () => {
      await invalidate();
      await queryClient.invalidateQueries({ queryKey: queryKeys.storyVersions(projectId) });
    },
  });
}

export function useStructure(projectId: string) {
  return useMutation({
    mutationFn: async (body: StructureBody): Promise<Job> => {
      const { data, response } = await api.POST("/api/v1/projects/{project_id}/story:structure", {
        params: { path: { project_id: projectId } },
        body,
      });
      if (!data) {
        const detail = (await response.clone().json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(typeof detail.detail === "string" ? detail.detail : "could not start structuring");
      }
      return data;
    },
  });
}

export function useApprove(projectId: string) {
  const invalidate = useInvalidateStory(projectId);
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const { data, response } = await api.POST("/api/v1/projects/{project_id}/story:approve", {
        params: { path: { project_id: projectId } },
      });
      if (!data) {
        const detail = (await response.clone().json().catch(() => ({}))) as { detail?: unknown };
        throw new Error(typeof detail.detail === "string" ? detail.detail : "could not approve the story");
      }
      return data;
    },
    onSuccess: async () => {
      await invalidate();
      await queryClient.invalidateQueries({ queryKey: queryKeys.storyVersions(projectId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.stages(projectId) });
    },
  });
}

/** Polls a job every second while it is queued or running. */
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: queryKeys.job(jobId ?? ""),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1000 : false;
    },
    queryFn: async (): Promise<Job> => {
      const { data } = await api.GET("/api/v1/jobs/{job_id}", { params: { path: { job_id: jobId ?? "" } } });
      if (!data) throw new Error("could not load the job");
      return data;
    },
  });
}

export async function downloadStory(projectId: string): Promise<void> {
  const res = await globalThis.fetch(`/api/v1/projects/${projectId}/story/export`);
  if (!res.ok) throw new Error("could not export the story");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "story.yaml";
  a.click();
  URL.revokeObjectURL(url);
}
