import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "./client";
import { detailOf } from "./http";
import type { Job } from "./shots";

export type CueKind = "music" | "sfx" | "ambience" | "silence";
export type CueState = "suggested" | "draft" | "ready" | "stale";

export interface CueTime {
  scene: string;
  at?: "scene_start" | "scene_end";
  offset?: number;
}

/** A cue as the server accepts it (a story.yaml `audio` entry). */
export interface CueBody {
  id: string;
  kind: CueKind;
  start: CueTime;
  end?: CueTime;
  duration?: number;
  prompt?: string;
  source?: "generate" | "file";
  gain_db?: number;
  fade_in_s?: number;
  fade_out_s?: number;
  duck?: boolean;
  state?: "suggested";
}

export interface AudioTake {
  id: string;
  take_no: number;
  seed: number;
  model: string;
  prompt: string;
  duration_s: number;
  url: string;
  picked: boolean;
  stale: boolean;
}

export interface Cue extends Omit<CueBody, "state" | "source"> {
  order: number;
  state: CueState;
  source: string;
  start_s: number;
  end_s: number;
  duration_s: number;
  licence: string;
  file_name?: string;
  picked_take_id: string | null;
  takes: AudioTake[];
  job: Job | null;
  flags?: Array<"ends_after_reel">;
}

export interface MixSettings {
  duck_db: number;
  attack_s: number;
  release_s: number;
  silence_fade_s: number;
}

export interface AudioState {
  engine: { ok: boolean; message: string };
  legacy_music_hint?: boolean;
  settings: MixSettings;
  scenes?: Array<{ id: string; start_s: number; end_s: number }>;
  skipped_count?: number;
  cues: Cue[];
}

/** The server refused a cue edit; `errors` lists each problem with its path. */
export class CueInvalidError extends Error {
  errors: Array<{ path: string; message: string }>;
  constructor(errors: Array<{ path: string; message: string }>) {
    super(errors.map((e) => e.message).join(" "));
    this.errors = errors;
  }
}

const base = (projectId: string) => `/api/v1/projects/${projectId}/audio`;

export function useAudio(projectId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.audio(projectId),
    enabled,
    refetchInterval: (query) => {
      const busy = query.state.data?.cues.some((c) => c.job?.status === "queued" || c.job?.status === "running");
      return busy ? 1000 : false;
    },
    queryFn: async (): Promise<AudioState> => {
      const res = await globalThis.fetch(base(projectId));
      if (!res.ok) throw new Error(await detailOf(res, "could not load the sound cues"));
      return (await res.json()) as AudioState;
    },
  });
}

async function send<T>(url: string, init: RequestInit, fallback: string): Promise<T> {
  const res = await globalThis.fetch(url, init);
  if (res.status === 422) {
    const body = (await res.clone().json().catch(() => ({}))) as {
      detail?: unknown;
      errors?: Array<{ path: string; message: string }>;
    };
    if (Array.isArray(body.errors)) throw new CueInvalidError(body.errors);
  }
  if (!res.ok) throw new Error(await detailOf(res, fallback));
  return (await res.json()) as T;
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body ?? {}),
});

export type CueAction =
  | { name: "add"; cue: CueBody }
  | { name: "update"; cue: CueBody }
  | { name: "delete"; id: string }
  | { name: "move"; id: string; direction: "up" | "down" }
  | { name: "approve"; id: string }
  | { name: "approve-all" }
  | { name: "dismiss"; id: string }
  | { name: "select-take"; id: string; takeId: string }
  | { name: "generate"; id: string }
  | { name: "upload"; id: string; file: File }
  | { name: "settings"; values: Partial<MixSettings> }
  | { name: "preview-mix" };

function request(projectId: string, a: CueAction): Promise<unknown> {
  const root = base(projectId);
  switch (a.name) {
    case "add":
      return send(`${root}/cues`, json("POST", a.cue), "could not add the cue");
    case "update":
      return send(`${root}/cues/${a.cue.id}`, json("PUT", a.cue), "could not save the cue");
    case "delete":
      return send(`${root}/cues/${a.id}`, { method: "DELETE" }, "could not delete the cue");
    case "move":
      return send(`${root}/cues/${a.id}:move`, json("POST", { direction: a.direction }), "could not move the cue");
    case "approve":
      return send(`${root}/cues/${a.id}:approve`, json("POST"), "could not approve the cue");
    case "approve-all":
      return send(`${root}/cues:approve-all`, json("POST"), "could not approve the cues");
    case "dismiss":
      return send(`${root}/cues/${a.id}:dismiss`, json("POST"), "could not dismiss the cue");
    case "select-take":
      return send(`${root}/cues/${a.id}:select-take`, json("POST", { take_id: a.takeId }), "could not pick that take");
    case "generate":
      return send(`${root}/cues/${a.id}:generate`, json("POST"), "could not start generating");
    case "upload": {
      const form = new FormData();
      form.append("file", a.file);
      return send(`${root}/cues/${a.id}:upload`, { method: "POST", body: form }, "could not upload that file");
    }
    case "settings":
      return send(`${root}/settings`, json("PUT", a.values), "could not save the setting");
    case "preview-mix":
      return send(`${root}:preview-mix`, json("POST"), "could not start the preview");
  }
}

export function useAudioMutations(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (action: CueAction) => request(projectId, action),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.audio(projectId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.assembly(projectId) });
      await queryClient.invalidateQueries({ queryKey: queryKeys.stale(projectId) });
    },
  });
}
