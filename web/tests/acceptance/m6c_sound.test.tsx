import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LicenceDialog } from "@/assembly/LicenceDialog";
import { SoundScreen } from "@/sound/SoundScreen";
import { json, project, renderApp, stubFetch } from "./helpers";

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

afterEach(() => vi.unstubAllGlobals());

let played = 0;
beforeEach(() => {
  played = 0;
  Object.defineProperty(HTMLMediaElement.prototype, "play", {
    configurable: true,
    value: () => {
      played += 1;
      return Promise.resolve();
    },
  });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: () => {} });
});

type Obj = Record<string, unknown>;

function take(n: number, over: Obj = {}): Obj {
  return {
    id: `t${n}`, take_no: n, seed: n, model: "audio-model", prompt: "p", duration_s: 3,
    url: `/media/t${n}`, picked: n === 1, stale: false, ...over,
  };
}

function mkCue(id: string, over: Obj = {}): Obj {
  return {
    id, kind: "music", order: 1, state: "ready", start: { scene: "s1", at: "scene_start", offset: 0 },
    duration: 3, prompt: "festive shehnai", source: "generate", start_s: 0, end_s: 3, duration_s: 3,
    licence: "Apache-2.0", picked_take_id: "t1", takes: [take(1)], job: null, ...over,
  };
}

function audio(cues: Obj[], over: Obj = {}): Obj {
  return {
    engine: { ok: true, message: "" },
    settings: { duck_db: 9, attack_s: 0.15, release_s: 0.4, silence_fade_s: 0.08 },
    cues,
    ...over,
  };
}

interface Call { method: string; path: string; body: string }

function screenWith(state: Obj, onBack = () => {}, onContinue = () => {}) {
  const calls: Call[] = [];
  stubFetch([
    async (url, init) => {
      if (url.pathname === `${API}/audio` && init?.method === "GET") return json(state);
      if (init?.method && init.method !== "GET") {
        const body = typeof init.body === "string" ? init.body : init.body instanceof FormData ? "form" : "";
        calls.push({ method: init.method, path: url.pathname, body });
        if (url.pathname.endsWith(":generate")) return json({ id: "j1", type: "gen_audio_cue" }, 202);
        if (url.pathname.endsWith(":preview-mix")) return json({ id: "j2", type: "assemble_preview" }, 202);
        return json(state);
      }
      return undefined;
    },
  ]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SoundScreen projectId={ID} onBack={onBack} onContinue={onContinue} />
    </QueryClientProvider>,
  );
  return calls;
}

const row = (id: string) => screen.findByRole("listitem", { name: `Cue ${id}` });
const lastCall = (calls: Call[]) => calls[calls.length - 1];

describe("cue list", () => {
  it("lists cues in order with source, start, duration, state and licence", async () => {
    screenWith(
      audio([
        mkCue("m1"),
        mkCue("fx1", { kind: "sfx", order: 2, source: "generate", start_s: 2.5, end_s: 3.7, duration_s: 1.2, state: "draft", licence: "", picked_take_id: null, takes: [] }),
        mkCue("f1", { kind: "sfx", order: 3, source: "file", state: "stale", licence: "Your file: mine", file_name: "gong.wav" }),
      ]),
    );
    expect(await screen.findByRole("heading", { name: "Sound" })).toBeTruthy();
    const items = screen.getAllByRole("listitem").filter((li) => li.getAttribute("aria-label")?.startsWith("Cue "));
    expect(items.map((li) => li.getAttribute("aria-label"))).toEqual(["Cue m1", "Cue fx1", "Cue f1"]);
    const m1 = await row("m1");
    expect(m1.textContent).toMatch(/1/);
    expect(m1.textContent).toMatch(/music/i);
    expect(m1.textContent).toMatch(/Generate/);
    expect(m1.textContent).toMatch(/3 s/);
    expect(m1.textContent).toMatch(/Ready/);
    expect(m1.textContent).toMatch(/Apache-2\.0/);
    const fx = await row("fx1");
    expect(fx.textContent).toMatch(/2\.5 s/);
    expect(fx.textContent).toMatch(/1\.2 s/);
    expect(fx.textContent).toMatch(/Draft/);
    const f1 = await row("f1");
    expect(f1.textContent).toMatch(/File/);
    expect(f1.textContent).toMatch(/Needs update/);
    expect(f1.textContent).toMatch(/Your file: mine/);
  });

  it("shows the empty state and the hint for the old music note", async () => {
    screenWith(audio([], { legacy_music_hint: true }));
    expect(
      await screen.findByText("No sound cues yet. Add a cue or let the structuring step suggest some from your storyline."),
    ).toBeTruthy();
    expect(screen.getByText("This story uses the old music note. Add cues to design the sound.")).toBeTruthy();
  });

  it("shows the hint only when the server asks for it", async () => {
    screenWith(audio([]));
    await screen.findByRole("heading", { name: "Sound" });
    expect(screen.queryByText("This story uses the old music note. Add cues to design the sound.")).toBeNull();
  });

  it("shows the notes for a cue running past the reel, a missing licence note and skipped cues", async () => {
    screenWith(
      audio(
        [
          mkCue("long", { flags: ["ends_after_reel"] }),
          mkCue("up", { source: "file", licence: "No licence note", order: 2 }),
        ],
        { skipped_count: 2 },
      ),
    );
    expect(await screen.findByText("Ends after the reel.")).toBeTruthy();
    expect((await row("up")).textContent).toMatch(/No licence note/);
    expect(screen.getByText("2 cues have no audio and are left out of the mix.")).toBeTruthy();
  });

  it("goes back and next", async () => {
    const back = vi.fn();
    const next = vi.fn();
    screenWith(audio([mkCue("m1")]), back, next);
    await userEvent.click(await screen.findByRole("button", { name: "Back" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(back).toHaveBeenCalledTimes(1);
    expect(next).toHaveBeenCalledTimes(1);
  });
});

describe("cue actions", () => {
  it("adds a cue from the form", async () => {
    const calls = screenWith(audio([]));
    await userEvent.click(await screen.findByRole("button", { name: "Add cue" }));
    await userEvent.type(screen.getByLabelText("Cue id"), "gong1");
    await userEvent.selectOptions(screen.getByLabelText("Kind"), "sfx");
    await userEvent.type(screen.getByLabelText("Duration (s)"), "1.5");
    await userEvent.type(screen.getByLabelText("Prompt"), "gong slam");
    await userEvent.click(screen.getByRole("button", { name: "Save cue" }));
    await waitFor(() => expect(calls.some((c) => c.method === "POST" && c.path === `${API}/audio/cues`)).toBe(true));
    const body = JSON.parse(calls.find((c) => c.path === `${API}/audio/cues`)?.body ?? "{}") as Obj;
    expect(body).toMatchObject({ id: "gong1", kind: "sfx", duration: 1.5, prompt: "gong slam", source: "generate" });
    expect((body.start as Obj).scene).toBeTruthy();
  });

  it("offers every form field by label", async () => {
    screenWith(audio([]));
    await userEvent.click(await screen.findByRole("button", { name: "Add cue" }));
    for (const label of [
      "Cue id", "Kind", "Scene", "Offset (s)", "Duration (s)", "Prompt", "Source", "Gain (dB)", "Fade in (s)",
      "Fade out (s)", "Duck under dialogue",
    ]) {
      expect(screen.getByLabelText(label)).toBeTruthy();
    }
  });

  it("edits a cue and saves it with PUT", async () => {
    const calls = screenWith(audio([mkCue("m1")]));
    await userEvent.click(await screen.findByRole("button", { name: "Edit cue m1" }));
    const prompt = screen.getByLabelText("Prompt");
    expect((prompt as HTMLTextAreaElement | HTMLInputElement).value).toBe("festive shehnai");
    await userEvent.clear(prompt);
    await userEvent.type(prompt, "calmer sarangi");
    await userEvent.click(screen.getByRole("button", { name: "Save cue" }));
    await waitFor(() => expect(calls.some((c) => c.method === "PUT")).toBe(true));
    expect(lastCall(calls)?.path).toBe(`${API}/audio/cues/m1`);
    expect(JSON.parse(lastCall(calls)?.body ?? "{}")).toMatchObject({ id: "m1", prompt: "calmer sarangi" });
  });

  it("asks before deleting and deletes on confirm", async () => {
    const calls = screenWith(audio([mkCue("m1")]));
    await userEvent.click(await screen.findByRole("button", { name: "Delete cue m1" }));
    const dlg = await screen.findByRole("dialog", { name: "Delete cue m1?" });
    await userEvent.click(within(dlg).getByRole("button", { name: "Cancel" }));
    expect(calls.filter((c) => c.method === "DELETE")).toEqual([]);
    await userEvent.click(screen.getByRole("button", { name: "Delete cue m1" }));
    await userEvent.click(within(await screen.findByRole("dialog", { name: "Delete cue m1?" })).getByRole("button", { name: "Delete" }));
    await waitFor(() => expect(calls.some((c) => c.method === "DELETE")).toBe(true));
    expect(lastCall(calls)?.path).toBe(`${API}/audio/cues/m1`);
  });

  it("moves a cue up and down", async () => {
    const calls = screenWith(audio([mkCue("a"), mkCue("b", { order: 2 })]));
    await userEvent.click(await screen.findByRole("button", { name: "Move cue b up" }));
    await waitFor(() => expect(calls.length).toBe(1));
    expect(lastCall(calls)).toMatchObject({ method: "POST", path: `${API}/audio/cues/b:move` });
    expect(JSON.parse(lastCall(calls)?.body ?? "{}")).toEqual({ direction: "up" });
    await userEvent.click(screen.getByRole("button", { name: "Move cue a down" }));
    await waitFor(() => expect(calls.length).toBe(2));
    expect(JSON.parse(lastCall(calls)?.body ?? "{}")).toEqual({ direction: "down" });
  });

  it("plays the picked take", async () => {
    screenWith(audio([mkCue("m1")]));
    await userEvent.click(await screen.findByRole("button", { name: "Play m1" }));
    await waitFor(() => expect(played).toBeGreaterThan(0));
  });

  it("re-takes a cue that has a take, and offers Generate when it has none", async () => {
    const calls = screenWith(audio([mkCue("m1"), mkCue("fx1", { order: 2, state: "draft", picked_take_id: null, takes: [] })]));
    await userEvent.click(await screen.findByRole("button", { name: "Re-take m1" }));
    await waitFor(() => expect(calls.length).toBe(1));
    expect(lastCall(calls)).toMatchObject({ method: "POST", path: `${API}/audio/cues/m1:generate` });
    await userEvent.click(screen.getByRole("button", { name: "Generate fx1" }));
    await waitFor(() => expect(calls.length).toBe(2));
    expect(lastCall(calls)?.path).toBe(`${API}/audio/cues/fx1:generate`);
    expect(screen.queryByRole("button", { name: "Re-take fx1" })).toBeNull();
  });

  it("lists takes and picks an earlier one", async () => {
    const calls = screenWith(audio([mkCue("m1", { takes: [take(1), take(2, { picked: true })], picked_take_id: "t2" })]));
    await userEvent.click(await screen.findByRole("button", { name: "Takes for m1" }));
    expect(await screen.findByText("take 1")).toBeTruthy();
    expect(screen.getByText("take 2")).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Use this take" }).length).toBeGreaterThanOrEqual(1);
    await userEvent.click(screen.getAllByRole("button", { name: "Use this take" })[0] as HTMLElement);
    await waitFor(() => expect(calls.length).toBe(1));
    expect(lastCall(calls)?.path).toBe(`${API}/audio/cues/m1:select-take`);
    expect(JSON.parse(lastCall(calls)?.body ?? "{}")).toEqual({ take_id: "t1" });
  });

  it("uploads a file for a file cue", async () => {
    const calls = screenWith(audio([mkCue("f1", { source: "file", state: "draft", picked_take_id: null, takes: [] })]));
    const input = await screen.findByLabelText("Upload file for f1");
    const file = new File([new Uint8Array([82, 73, 70, 70])], "gong.wav", { type: "audio/wav" });
    await userEvent.upload(input, file);
    await waitFor(() => expect(calls.some((c) => c.path === `${API}/audio/cues/f1:upload`)).toBe(true));
    expect(calls.find((c) => c.path === `${API}/audio/cues/f1:upload`)?.method).toBe("POST");
  });

  it("has no upload control on a generated cue", async () => {
    screenWith(audio([mkCue("m1")]));
    await screen.findByRole("button", { name: "Edit cue m1" });
    expect(screen.queryByLabelText("Upload file for m1")).toBeNull();
  });

  it("previews the full mix", async () => {
    const calls = screenWith(audio([mkCue("m1")]));
    await userEvent.click(await screen.findByRole("button", { name: "Preview full mix" }));
    await waitFor(() => expect(calls.length).toBe(1));
    expect(lastCall(calls)).toMatchObject({ method: "POST", path: `${API}/audio:preview-mix` });
  });

  it("saves the ducking amount on blur", async () => {
    const calls = screenWith(audio([mkCue("m1")]));
    const field = (await screen.findByLabelText("Duck amount (dB)")) as HTMLInputElement;
    expect(field.value).toBe("9");
    await userEvent.clear(field);
    await userEvent.type(field, "12");
    fireEvent.blur(field);
    await waitFor(() => expect(calls.some((c) => c.path === `${API}/audio/settings`)).toBe(true));
    const put = calls.find((c) => c.path === `${API}/audio/settings`);
    expect(put?.method).toBe("PUT");
    expect(JSON.parse(put?.body ?? "{}")).toEqual({ duck_db: 12 });
  });
});

describe("suggested cues and the engine", () => {
  it("approves or dismisses a suggested cue and keeps Generate off until approved", async () => {
    const calls = screenWith(
      audio([mkCue("sug1", { state: "suggested", picked_take_id: null, takes: [] })]),
    );
    const r = await row("sug1");
    expect(r.textContent).toMatch(/Suggested/);
    const gen = screen.getByRole("button", { name: "Generate sug1" }) as HTMLButtonElement;
    expect(gen.disabled).toBe(true);
    await userEvent.click(within(r).getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls.length).toBe(1));
    expect(lastCall(calls)).toMatchObject({ method: "POST", path: `${API}/audio/cues/sug1:approve` });
    await userEvent.click(within(r).getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(calls.length).toBe(2));
    expect(lastCall(calls)?.path).toBe(`${API}/audio/cues/sug1:dismiss`);
  });

  it("disables generate actions with the engine hint when the engine is not available", async () => {
    screenWith(
      audio([mkCue("m1")], { engine: { ok: false, message: "Audio model is not installed." } }),
    );
    const btn = (await screen.findByRole("button", { name: "Re-take m1" })) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(screen.getByText("Audio model is not installed.")).toBeTruthy();
  });
});

describe("licence dialog", () => {
  it("lists an upload without a note and an audio model warning", () => {
    render(
      <LicenceDialog
        warnings={[
          { cue_id: "f1", kind: "sfx", file_name: "gong.wav", licence: "" },
          { cue_id: "m1", kind: "music", model: "acme/music-x", version: "r2", licence: "CC-BY-NC-4.0" },
          { model: "flux-x", version: "r1", licence: "Non-Commercial License" },
        ] as never}
        onExport={() => {}}
        onCancel={() => {}}
      />,
    );
    const dlg = screen.getByRole("dialog", { name: "Licence check before export" });
    expect(within(dlg).getByText("gong.wav - Licence note not filled in")).toBeTruthy();
    expect(within(dlg).getByText("m1 acme/music-x r2 - CC-BY-NC-4.0")).toBeTruthy();
    expect(within(dlg).getByText("flux-x r1 - Non-Commercial License")).toBeTruthy();
    expect(within(dlg).getByRole("button", { name: "Export anyway" })).toBeTruthy();
    expect(within(dlg).getByRole("button", { name: "Cancel" })).toBeTruthy();
  });
});

describe("project flow", () => {
  function app(path: string) {
    stubFetch([
      async (url, init) => {
        const get = !init?.method || init.method === "GET";
        if (get && url.pathname === `/api/v1/projects/${ID}`) return json(project({ stage: "SHOTS_APPROVED" }));
        if (get && url.pathname === `${API}/audio`) return json(audio([mkCue("m1")]));
        return undefined;
      },
    ]);
    renderApp(path);
  }

  it("shows the Sound screen at ?screen=sound once the shots are approved", async () => {
    app(`/projects/${ID}?screen=sound`);
    expect(await screen.findByRole("heading", { name: "Sound" })).toBeTruthy();
    expect(await screen.findByRole("listitem", { name: "Cue m1" })).toBeTruthy();
  });

  it("moves from Sound to Assembly with Next, and Assembly goes back to Sound", async () => {
    app(`/projects/${ID}?screen=sound`);
    await userEvent.click(await screen.findByRole("button", { name: "Next" }));
    expect((await screen.findAllByRole("button", { name: "Back to Sound" })).length).toBeGreaterThan(0);
    await userEvent.click(screen.getAllByRole("button", { name: "Back to Sound" })[0] as HTMLElement);
    expect(await screen.findByRole("heading", { name: "Sound" })).toBeTruthy();
  });
});
