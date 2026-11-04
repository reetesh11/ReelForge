import createClient from "openapi-fetch";
import type { paths } from "./schema";

export const api = createClient<paths>({
  baseUrl: window.location.origin,
  // Resolve fetch at call time so the global can be replaced (tests, polyfills).
  fetch: (request: Request) => globalThis.fetch(request),
});

export const queryKeys = {
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  stages: (id: string) => ["project", id, "stages"] as const,
  story: (id: string) => ["project", id, "story"] as const,
  storyVersions: (id: string) => ["project", id, "story", "versions"] as const,
  storyVersion: (id: string, n: number) => ["project", id, "story", "version", n] as const,
  cast: (id: string) => ["project", id, "stages", "cast"] as const,
  voices: (id: string) => ["project", id, "stages", "voices"] as const,
  voiceModel: ["voice-model"] as const,
  stale: (id: string) => ["project", id, "stale"] as const,
  job: (jobId: string) => ["job", jobId] as const,
  storySchema: ["story-schema"] as const,
  jobs: ["jobs"] as const,
  library: ["library"] as const,
  libraryCharacter: (id: string) => ["library", id] as const,
  health: ["health"] as const,
};
