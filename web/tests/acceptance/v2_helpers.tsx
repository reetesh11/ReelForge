import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, useLocation, useNavigate } from "react-router-dom";
import { vi } from "vitest";
import { AppRoutes } from "@/AppRoutes";
import { FakeWebSocket, json, newClient, project, stage, stubFetch, type Route } from "./helpers";

export const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
export const API = `/api/v1/projects/${ID}`;

export const LABELS = ["Story", "Cast", "Voices", "Key frames", "Shots", "Assembly"] as const;
export const KEYS = ["story", "cast", "voices", "frames", "shots", "assembly"] as const;

/** Six stages; `states[i]` is the state, stages from index `unlocked` on are locked. */
export function sixStages(states: string[], unlocked: number, progress: Record<number, number> = {}) {
  return LABELS.map((label, i) =>
    stage(KEYS[i] as string, label, states[i] ?? "not_started", progress[i] ?? null, i >= unlocked),
  );
}

export const YAML_TEXT = `version: 1
title: "Tale"
language: english
style: "3D cartoon"
aspect: "9:16"
fps: 24
target_seconds: 12
characters:
  tomato:
    name: "Tamatar"
    look: |-
      round red tomato
      with a leaf hat
scenes:
  - id: s1
    setting: "A kitchen"
    speaker: tomato
    line: |-
      Namaste doston,
      aaj kya banayein?
    action: |-
      Tamatar waves
      at the camera
    framing: wide
    duration: 3.0
  - id: s2
    action: "Tamatar smiles"
    duration: 3.0
`;

export function storyVersion(approved: boolean) {
  return {
    id: "v1",
    version: 1,
    is_current: true,
    approved_at: approved ? "2026-11-01T10:00:00Z" : null,
    created_at: "2026-11-01T10:00:00Z",
  };
}

export function castBody(over: Record<string, unknown> = {}, character: Record<string, unknown> = {}) {
  return {
    stage: "STORY_APPROVED",
    approved_count: 0,
    total: 1,
    image_backend: { kind: "mock", reachable: true, port: 7860, mflux_available: false },
    characters: [
      {
        key: "tomato",
        name: "Tamatar",
        aliases: [],
        look: "round red tomato",
        bible_line: "round red tomato, plain background",
        bible_source: "llm",
        state: "ready",
        candidates: [
          { id: "a1", kind: "generated", prompt: "p", seed: 5, model: "m", model_key: "image", image_url: "/media/a1", width: 576, height: 1024 },
          { id: "a2", kind: "generated", prompt: "p", seed: 6, model: "m", model_key: "image", image_url: "/media/a2", width: 576, height: 1024 },
        ],
        approved: false,
        voice_reference: "",
        ...character,
      },
    ],
    ...over,
  };
}

const vtake = (n: number, active: boolean) => ({
  id: `t${n}`, take_no: n, seed: n, duration_s: 3.1, active, approved: false, stale: false, audio_url: `/media/t${n}`,
});

export function voiceLine(sid: string, over: Record<string, unknown> = {}) {
  return {
    scene_id: sid, position: 1, speaker: "tomato", speaker_name: "Tamatar", text: `Line of ${sid}`, language: "hi",
    state: "ready", speed: 1, pause_before: 0, pause_after: 0, takes: [vtake(1, true)], duration_s: 3.1,
    shot_length_stale: false, ...over,
  };
}

export function voicesBody(lines: unknown[], over: Record<string, unknown> = {}) {
  const rows = lines as Array<{ state: string }>;
  return {
    stage: "CAST_APPROVED",
    voice_model: { key: "omnivoice", label: "OmniVoice", model_id: "m" },
    presets: [],
    approved_count: rows.filter((l) => l.state === "approved").length,
    total: rows.length,
    stale_count: rows.filter((l) => l.state === "stale").length,
    characters: [{ key: "tomato", name: "Tamatar", voice: null }],
    lines,
    job: null,
    ...over,
  };
}

const ftake = (n: number, active: boolean) => ({
  id: `t${n}`, take_no: n, seed: n, active, approved: false, stale: false, source: "render", image_url: `/media/t${n}`, inputs: ["m1"],
});

export function frame(sid: string, over: Record<string, unknown> = {}) {
  return {
    scene_id: sid, position: 1, characters: [{ key: "tomato", name: "Tamatar" }],
    master: { key: "tomato", name: "Tamatar", artifact_id: "m1" }, framing: "medium", state: "ready",
    prompt: "A tomato waves", prompt_source: "llm", look_removed: false, takes: [ftake(1, true)], notes: {},
    continue_previous: false, job: null, ...over,
  };
}

export function framesBody(frames: unknown[], over: Record<string, unknown> = {}) {
  const rows = frames as Array<{ state: string }>;
  return {
    stage: "VOICES_APPROVED",
    approved_count: rows.filter((f) => f.state === "approved").length,
    total: rows.length,
    stale_count: rows.filter((f) => f.state === "stale").length,
    jobs: [],
    frames,
    ...over,
  };
}

const stake = (n: number, active: boolean) => ({
  id: `t${n}`, take_no: n, seed: n, active, approved: false, stale: false, source: "render", quality: "draft",
  video_url: `/media/t${n}`, last_frame_id: `l${n}`, inputs: [],
});

export function shot(sid: string, over: Record<string, unknown> = {}) {
  return {
    scene_id: sid, position: 1, shot_type: "talking", shot_type_auto: "talking", quality: "draft", width: 320,
    height: 576, frames: 81, shot_length_s: 3.375, motion_prompt: "slow push in", state: "ready", blockers: [],
    frame_url: "/media/f1", takes: [stake(1, true)], job: null, ...over,
  };
}

export function shotsBody(shots: unknown[], over: Record<string, unknown> = {}) {
  const rows = shots as Array<{ state: string }>;
  return {
    stage: "FRAMES_APPROVED",
    engine: { ok: true, message: "" },
    approved_count: rows.filter((s) => s.state === "approved").length,
    total: rows.length,
    stale_count: rows.filter((s) => s.state === "stale").length,
    shots,
    queue: { paused: false, rows: [], total_shots: 0, total_s: 0, total_text: "", running: null },
    ...over,
  };
}

export function assemblyBody(over: Record<string, unknown> = {}) {
  return {
    stage: "SHOTS_APPROVED", blocked_reason: null, edl: null, edl_hash: null, shots: [], caption_status: {},
    preview: { state: "none", step: null, progress: null, url: null, job_id: null, error: null, rebuild_in_s: null },
    export: { state: "idle", step: null, step_index: null, step_total: null, progress: null, job_id: null, failed_step: null, error: null },
    versions: [], licence_warnings: [], caption_presets: [], ...over,
  };
}

export type Scenario = {
  projectStage?: string;
  stages?: unknown[] | "fail";
  storyApproved?: boolean;
  stale?: Array<{ owner_type: string; owner_id: string }>;
  cast?: unknown;
  voices?: unknown;
  frames?: unknown;
  shots?: unknown;
  assembly?: unknown;
  extra?: Route[];
};

export function scenarioRoutes(s: Scenario): Route[] {
  return [
    ...(s.extra ?? []),
    (url) => (url.pathname === API ? json(project({ stage: s.projectStage ?? "STORY_APPROVED" })) : undefined),
    (url) =>
      url.pathname === `${API}/stages`
        ? s.stages === "fail"
          ? json({ detail: "boom" }, 500)
          : json({ stages: s.stages ?? sixStages(["approved", "needs_review"], 2) })
        : undefined,
    (url, init) =>
      url.pathname === `${API}/story` && init?.method === "GET"
        ? json({ ...storyVersion(s.storyApproved ?? true), yaml_text: YAML_TEXT })
        : undefined,
    (url) => (url.pathname === `${API}/story/versions` ? json([storyVersion(s.storyApproved ?? true)]) : undefined),
    (url) =>
      url.pathname === `${API}/stale`
        ? json({ items: (s.stale ?? []).map((i) => ({ ...i, artifact_id: "x", kind: "k" })) })
        : undefined,
    (url) => (url.pathname === "/api/v1/story/schema" ? json({ type: "object" }) : undefined),
    (url) => (url.pathname === `${API}/cast` ? json(s.cast ?? castBody()) : undefined),
    (url) => (url.pathname === `${API}/voices` ? json(s.voices ?? voicesBody([voiceLine("s1")])) : undefined),
    (url) => (url.pathname === `${API}/frames` ? json(s.frames ?? framesBody([frame("s1")])) : undefined),
    (url) => (url.pathname === `${API}/shots` ? json(s.shots ?? shotsBody([shot("s1")])) : undefined),
    (url) =>
      url.pathname.startsWith(`${API}/assembly`) ? json(s.assembly ?? assemblyBody()) : undefined,
  ];
}

function Probe() {
  const loc = useLocation();
  const nav = useNavigate();
  return (
    <div>
      <span data-testid="probe-location">{`${loc.pathname}${loc.search}`}</span>
      <button type="button" data-testid="probe-back" onClick={() => void nav(-1)}>
        probe back
      </button>
    </div>
  );
}

/** Like renderApp, plus a location readout and a history-back probe outside the app. */
export function renderWithProbe(path: string, client: QueryClient = newClient()) {
  vi.stubGlobal("WebSocket", FakeWebSocket);
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <AppRoutes />
        <Probe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

export function mount(path: string, s: Scenario) {
  stubFetch(scenarioRoutes(s));
  return renderWithProbe(path);
}
