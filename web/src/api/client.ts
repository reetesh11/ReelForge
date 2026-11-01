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
  jobs: ["jobs"] as const,
  health: ["health"] as const,
};
