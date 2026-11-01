import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, queryKeys } from "./client";
import type { components } from "./schema";

export type Project = components["schemas"]["ProjectOut"];
export type StageInfo = components["schemas"]["StageInfo"];
export type StageState = StageInfo["state"];
export type HealthReport = components["schemas"]["HealthOut"];

export class NotFoundError extends Error {}

export function useProjects() {
  return useQuery({
    queryKey: queryKeys.projects,
    queryFn: async (): Promise<Project[]> => {
      const { data, error } = await api.GET("/api/v1/projects");
      if (error || !data) throw new Error("could not load projects");
      return data;
    },
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (title: string): Promise<Project> => {
      const { data, error } = await api.POST("/api/v1/projects", { body: { title } });
      if (error || !data) throw new Error("could not create project");
      return data;
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.projects }),
  });
}

export function useProject(projectId: string) {
  return useQuery({
    queryKey: queryKeys.project(projectId),
    queryFn: async (): Promise<Project> => {
      const { data, response } = await api.GET("/api/v1/projects/{project_id}", {
        params: { path: { project_id: projectId } },
      });
      if (response.status === 404) throw new NotFoundError("project not found");
      if (!data) throw new Error("could not load project");
      return data;
    },
  });
}

export function useStages(projectId: string) {
  return useQuery({
    queryKey: queryKeys.stages(projectId),
    queryFn: async (): Promise<StageInfo[]> => {
      const { data } = await api.GET("/api/v1/projects/{project_id}/stages", {
        params: { path: { project_id: projectId } },
      });
      if (!data) throw new Error("could not load stages");
      return data.stages;
    },
  });
}

export function useHealth() {
  return useQuery({
    queryKey: queryKeys.health,
    queryFn: async (): Promise<HealthReport> => {
      const { data } = await api.GET("/health");
      if (!data) throw new Error("could not load health");
      return data;
    },
  });
}
