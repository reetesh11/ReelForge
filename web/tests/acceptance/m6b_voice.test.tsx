import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { VoiceBoardState, VoiceLine } from "@/api/voice";
import { VoiceBoard } from "@/voice/VoiceBoard";
import { VoiceSetup } from "@/voice/VoiceSetup";
import { json, project, renderApp, stage, stubFetch } from "./helpers";

afterEach(() => vi.unstubAllGlobals());

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

// ---- line card -------------------------------------------------------------------------------

function mkLine(over: Record<string, unknown> = {}): VoiceLine {
  return {
    scene_id: "s1",
    position: 1,
    speaker: "tomato",
    speaker_name: "Tamatar",
    text: "Tum kahan ho?",
    language: "hi",
    state: "ready",
    speed: 1,
    pause_before: 0,
    pause_after: 0,
    takes: [
      { id: "t1", take_no: 1, seed: 1, duration_s: 3.1, active: true, approved: false, stale: false, audio_url: "/media/t1" },
    ],
    duration_s: 3.1,
    shot_length_stale: false,
    ...over,
  } as unknown as VoiceLine;
}

function mkBoard(line: VoiceLine, mode: string): VoiceBoardState {
  return {
    stage: "CAST_APPROVED",
    voice_model: { key: "omnivoice", label: "OmniVoice", model_id: "m" },
    presets: [],
    approved_count: 0,
    total: 1,
    stale_count: 0,
    characters: [
      {
        key: "tomato",
        name: "Tamatar",
        voice: { mode, model: "omnivoice", voice_id: null, reference_text: "x", speed: 1, language: "hi", model_mismatch: false },
      },
    ],
    lines: [line],
    job: null,
  } as unknown as VoiceBoardState;
}

function board(line: VoiceLine, mode = "preset") {
  const calls: Array<{ method: string; path: string; body: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : null;
      const url = new URL(req ? req.url : String(input), "http://localhost");
      const method = req ? req.method : (init?.method ?? "GET");
      const body = req ? await req.clone().text() : String(init?.body ?? "");
      if (method !== "GET") calls.push({ method, path: url.pathname, body });
      if (url.pathname === `${API}/voices` && method === "GET") return json(mkBoard(line, mode));
      return json({ project_stage: "CAST_APPROVED", approved_count: 0, total: 1, line, emotion_clips: {} }, 200);
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <VoiceBoard projectId={ID} />
    </QueryClientProvider>,
  );
  return calls;
}

describe("line card", () => {
  it("shows the emotion picker with its options and posts set-emotion", async () => {
    const calls = board(mkLine({ emotion: "happy" }));
    const card = await screen.findByRole("group", { name: "Scene s1" });
    const picker = within(card).getByLabelText("Emotion") as HTMLSelectElement;
    expect([...picker.options].map((o) => [o.value, o.text])).toEqual([
      ["", "None"],
      ["happy", "Happy"],
      ["sad", "Sad"],
      ["fear", "Fear"],
      ["anger", "Anger"],
    ]);
    expect(picker.value).toBe("happy");
    await userEvent.selectOptions(picker, "sad");
    await waitFor(() => expect(calls.some((c) => c.path === `${API}/voices/lines/s1:set-emotion`)).toBe(true));
    const call = calls.find((c) => c.path.endsWith(":set-emotion"));
    expect(JSON.parse(call?.body ?? "{}")).toEqual({ emotion: "sad" });
    await userEvent.selectOptions(picker, "");
    await waitFor(() => expect(calls.filter((c) => c.path.endsWith(":set-emotion"))).toHaveLength(2));
    expect(JSON.parse(calls.filter((c) => c.path.endsWith(":set-emotion"))[1]?.body ?? "{}")).toEqual({ emotion: null });
  });

  it("has a closed 'How this will sound' panel that says default delivery when nothing is set", async () => {
    board(mkLine());
    const card = await screen.findByRole("group", { name: "Scene s1" });
    const summary = within(card).getByText("How this will sound");
    const details = summary.closest("details");
    expect(details).not.toBeNull();
    expect(details?.open).toBe(false);
    expect(within(card).getByText("Default delivery. No emotion settings applied.")).toBeTruthy();
  });

  it("lists the effective settings, the age band and the reference label", async () => {
    const effective = {
      emotion_applied: true,
      speed: 1,
      age_band: "elderly",
      phrases: [
        {
          text: "Mujhe akela chhod diya.",
          emotion: "sad",
          tags: ["[sigh]"],
          tag_position: "prefix",
          pitch: "low pitch",
          duration_scale: 1.25,
          duration_factor: 1.25,
          generation: { guidance_scale: 2 },
          post: { semitones: -2, gain_db: -3, pause_s: 0 },
          reference: "emotion",
          reference_label: "Sad reference clip",
        },
      ],
    };
    board(mkLine({ emotion: "sad", effective, settings_changed: true }));
    const card = await screen.findByRole("group", { name: "Scene s1" });
    const text = (card.querySelector("details")?.textContent ?? "").toLowerCase();
    for (const needle of ["sad", "[sigh]", "prefix", "low pitch", "1.25", "elderly", "sad reference clip"]) {
      expect(text).toContain(needle);
    }
    expect(within(card).getByText("Settings changed since this take")).toBeTruthy();
    expect(within(card).queryByText("Default delivery. No emotion settings applied.")).toBeNull();
  });

  it("says emotion is not applied for a voice that ignores it", async () => {
    board(mkLine({ emotion: "sad", effective: { emotion_applied: false, speed: 1, phrases: [] } }));
    const card = await screen.findByRole("group", { name: "Scene s1" });
    expect(within(card).getByText("Emotion is not applied for this voice.")).toBeTruthy();
  });

  it("shows clean text and starts the edit box from the raw markup", async () => {
    board(mkLine({ text: "Tum kahan ho? Mujhe akela.", edit_text: "Tum kahan ho? <sad>Mujhe akela.</sad>" }));
    const card = await screen.findByRole("group", { name: "Scene s1" });
    expect(within(card).getByText("Tum kahan ho? Mujhe akela.")).toBeTruthy();
    expect(card.querySelector("p")?.textContent).toBe("Tum kahan ho? Mujhe akela.");
    await userEvent.click(within(card).getByRole("button", { name: /edit/i }));
    const box = within(card).getByRole("textbox") as HTMLTextAreaElement;
    expect(box.value).toBe("Tum kahan ho? <sad>Mujhe akela.</sad>");
  });

  it("offers 'use this take as the reference' only for cloned voices and saves with an editable transcript", async () => {
    const calls = board(mkLine(), "cloned");
    const card = await screen.findByRole("group", { name: "Scene s1" });
    for (const e of ["Happy", "Sad", "Fear", "Anger"]) {
      expect(within(card).getByRole("button", { name: `Use this take as the ${e} reference` })).toBeTruthy();
    }
    await userEvent.click(within(card).getByRole("button", { name: "Use this take as the Happy reference" }));
    const field = within(card).getByLabelText("Reference transcript") as HTMLInputElement;
    expect(field.value).toBe("Tum kahan ho?");
    await userEvent.clear(field);
    await userEvent.type(field, "Tum kahan ho yaar");
    await userEvent.click(within(card).getByRole("button", { name: "Save reference" }));
    await waitFor(() => expect(calls.some((c) => c.path.endsWith("/emotion-clips/happy:from-take"))).toBe(true));
    const call = calls.find((c) => c.path.endsWith("/emotion-clips/happy:from-take"));
    expect(call?.path).toBe(`${API}/voices/characters/tomato/emotion-clips/happy:from-take`);
    expect(JSON.parse(call?.body ?? "{}")).toEqual({ scene_id: "s1", take_id: "t1", transcript: "Tum kahan ho yaar" });
  });

  it("does not offer reference buttons for a preset voice", async () => {
    board(mkLine(), "preset");
    const card = await screen.findByRole("group", { name: "Scene s1" });
    expect(within(card).queryByRole("button", { name: /Use this take as the/ })).toBeNull();
  });
});

// ---- voice setup -----------------------------------------------------------------------------

const PRESETS = [{ id: "asha", label: "Asha (female)" }];

function setup(voice: Record<string, unknown> | null, over: Record<string, unknown> = {}) {
  const props = {
    name: "Tamatar",
    voice: voice as never,
    presets: PRESETS,
    onSet: vi.fn(),
    onUpload: vi.fn(),
    onPreview: vi.fn(async () => "/media/sample"),
    onUploadEmotionClip: vi.fn(),
    onRemoveEmotionClip: vi.fn(),
    ...over,
  };
  render(<VoiceSetup {...(props as unknown as Parameters<typeof VoiceSetup>[0])} />);
  return props;
}

const cloned = { mode: "cloned", model: "omnivoice", voice_id: null, reference_text: "x", speed: 1, language: "hi", model_mismatch: false, clip_seconds: 7 };

describe("voice setup", () => {
  it("shows the age and band, or that no age is set", () => {
    setup(cloned, { age: 67, ageBand: "elderly", modelKey: "omnivoice" });
    expect(screen.getByText("Age 67 (elderly)")).toBeTruthy();
    expect(screen.queryByText("Experimental")).toBeNull();
  });

  it("says no age set and marks the Kokoro age mapping experimental", () => {
    setup({ ...cloned, mode: "preset", voice_id: "asha" }, { age: null, modelKey: "kokoro" });
    expect(screen.getByText("No age set")).toBeTruthy();
    expect(screen.getByText("Experimental")).toBeTruthy();
  });

  it("lists a row per emotion with its clip, and removes one", async () => {
    const clips = { sad: { url: "/media/c1", transcript: "udaas vakya", clip_seconds: 6 } };
    const props = setup(cloned, { emotionClips: clips });
    expect(screen.getByText("Emotion reference clips")).toBeTruthy();
    expect(screen.getByText("udaas vakya")).toBeTruthy();
    expect(screen.getAllByText("No clip. The neutral reference and emotion settings are used.")).toHaveLength(3);
    await userEvent.click(screen.getByRole("button", { name: "Remove Sad clip" }));
    expect(props.onRemoveEmotionClip).toHaveBeenCalledWith("sad");
    expect(screen.queryByRole("button", { name: "Remove Happy clip" })).toBeNull();
  });

  it("uploads a clip with a transcript for one emotion", async () => {
    const props = setup(cloned, { emotionClips: {} });
    const file = new File([new Uint8Array([1, 2, 3])], "udaas.wav", { type: "audio/wav" });
    await userEvent.upload(screen.getByLabelText("Upload clip for Sad"), file);
    await userEvent.type(screen.getByLabelText("Transcript for Sad"), "udaas vakya");
    await userEvent.click(screen.getAllByRole("button", { name: "Upload clip" })[1] as HTMLElement);
    expect(props.onUploadEmotionClip).toHaveBeenCalledTimes(1);
    const [emotion, sent, transcript] = props.onUploadEmotionClip.mock.calls[0] as unknown as [string, File, string];
    expect(emotion).toBe("sad");
    expect(sent.name).toBe("udaas.wav");
    expect(transcript).toBe("udaas vakya");
  });

  it("hides the emotion clips for preset and recorded voices", () => {
    setup({ ...cloned, mode: "preset", voice_id: "asha" }, { emotionClips: {} });
    expect(screen.queryByText("Emotion reference clips")).toBeNull();
  });
});

// ---- cast row --------------------------------------------------------------------------------

const YAML_TEXT = `version: 1
title: "Tale"
language: english
style: "3D cartoon"
aspect: "9:16"
fps: 24
target_seconds: 12
characters:
  tomato:
    name: "Tamatar"
    look: "round red tomato"
scenes:
  - id: s1
    action: "Tamatar waves"
    duration: 3.0
  - id: s2
    action: "Tamatar smiles"
    duration: 3.0
  - id: s3
    action: "Tamatar jumps"
    duration: 3.0
  - id: s4
    action: "Tamatar bows"
    duration: 3.0
`;

function castBody(extra: Record<string, unknown> = {}) {
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
        candidates: [],
        approved: false,
        voice_reference: "",
        ...extra,
      },
    ],
  };
}

function castRoutes(cast: unknown, extra: Array<(url: URL, init?: RequestInit) => Response | undefined>) {
  const stages = ["Story", "Cast", "Voices", "Key frames", "Shots", "Assembly"].map((l, i) =>
    stage(l.toLowerCase(), l, i === 0 ? "approved" : "not_started", null, i > 1),
  );
  const version = { id: "v1", version: 1, is_current: true, approved_at: "2026-11-01T10:00:00Z", created_at: "2026-11-01T10:00:00Z" };
  return [
    ...extra,
    (url: URL) => (url.pathname === API ? json(project()) : undefined),
    (url: URL) => (url.pathname === `${API}/stages` ? json({ stages }) : undefined),
    (url: URL) => (url.pathname === `${API}/story` ? json({ ...version, yaml_text: YAML_TEXT }) : undefined),
    (url: URL) => (url.pathname === `${API}/story/versions` ? json([version]) : undefined),
    (url: URL) => (url.pathname === `${API}/cast` ? json(cast) : undefined),
    (url: URL) => (url.pathname === "/api/v1/story/schema" ? json({ type: "object", additionalProperties: false }) : undefined),
  ];
}

describe("cast row age", () => {
  it("shows 'No age set', saves an age and shows the error message on 422", async () => {
    const posted: string[] = [];
    const setAge = (url: URL, init?: RequestInit) => {
      if (url.pathname === `${API}/cast/tomato:set-age` && init?.method === "POST") {
        posted.push(String(init.body));
        return json({ detail: "Age must be a whole number from 1 to 120." }, 422);
      }
      return undefined;
    };
    stubFetch(castRoutes(castBody(), [setAge]));
    renderApp(`/projects/${ID}`);
    const section = await screen.findByLabelText("Cast");
    expect(await within(section).findByText("No age set")).toBeTruthy();
    const input = within(section).getByLabelText("Age (years)");
    await userEvent.type(input, "200");
    await userEvent.click(within(section).getByRole("button", { name: "Save age" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(JSON.parse(posted[0] ?? "{}")).toEqual({ age: 200 });
    expect(await within(section).findByText("Age must be a whole number from 1 to 120.")).toBeTruthy();
  });

  it("shows the age and band when set", async () => {
    stubFetch(castRoutes(castBody({ age: 67, age_band: "elderly" }), []));
    renderApp(`/projects/${ID}`);
    const section = await screen.findByLabelText("Cast");
    expect(await within(section).findByText("Age 67 (elderly)")).toBeTruthy();
  });
});
