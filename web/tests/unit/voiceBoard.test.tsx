import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { VoiceBoardState, VoiceLine } from "@/api/voice";
import { VoiceBoard } from "@/voice/VoiceBoard";

afterEach(() => vi.unstubAllGlobals());

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

function take(n: number, active: boolean, dur = 3.1) {
  return {
    id: `t${n}`,
    take_no: n,
    seed: n,
    duration_s: dur,
    active,
    approved: false,
    stale: false,
    audio_url: `/media/t${n}`,
  };
}

function line(sid: string, over: Partial<VoiceLine> = {}): VoiceLine {
  return {
    scene_id: sid,
    position: 1,
    speaker: "tomato",
    speaker_name: "Tamatar",
    text: `Line of ${sid}`,
    language: "hi",
    state: "ready",
    speed: 1,
    pause_before: 0,
    pause_after: 0,
    takes: [take(1, false), take(2, true)],
    duration_s: 3.4,
    shot_length_stale: false,
    ...over,
  };
}

function board(lines: VoiceLine[], over: Partial<VoiceBoardState> = {}): VoiceBoardState {
  const texted = lines.filter((l) => l.state !== "no_dialogue");
  return {
    stage: "CAST_APPROVED",
    voice_model: { key: "omnivoice", label: "OmniVoice", model_id: "m" },
    presets: [],
    approved_count: texted.filter((l) => l.state === "approved").length,
    total: texted.length,
    stale_count: texted.filter((l) => l.state === "stale").length,
    characters: [
      { key: "tomato", name: "Tamatar", voice: null },
      {
        key: "potato",
        name: "Aloo",
        voice: {
          mode: "recorded",
          model: null,
          voice_id: null,
          reference_text: "",
          speed: 1,
          language: "hi",
          model_mismatch: false,
        },
      },
    ],
    lines,
    job: null,
    ...over,
  };
}

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function setup(state: VoiceBoardState) {
  const calls: Array<{ method: string; path: string; body: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : null;
      const url = new URL(req ? req.url : String(input), "http://localhost");
      const method = req ? req.method : (init?.method ?? "GET");
      const body = req ? await req.clone().text() : String(init?.body ?? "");
      if (method !== "GET") calls.push({ method, path: url.pathname, body });
      if (url.pathname === `${API}/voices` && method === "GET") return reply(state);
      if (url.pathname.includes("/voices:generate")) return reply({ id: "j1", type: "gen_voice_take" }, 202);
      if (url.pathname.includes(":shorten")) return reply({ proposal: "Chhota vakya" });
      return reply({ project_stage: "CAST_APPROVED", approved_count: 0, total: 1, line: line("s1") });
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <VoiceBoard projectId={ID} />
    </QueryClientProvider>,
  );
  return calls;
}

it("shows the top bar, counts and one group per scene", async () => {
  setup(board([line("s1", { state: "approved" }), line("s2", { takes: [], state: "no_take", duration_s: undefined })]));
  expect(await screen.findByText("1 of 2 lines approved")).toBeTruthy();
  expect(screen.getByText("1 line has no take yet")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Generate all lines" })).toBeTruthy();
  expect(screen.getByRole("button", { name: "Play all" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Regenerate stale items" })).toBeNull();
  const group = screen.getByRole("group", { name: "Scene s1" });
  expect(within(group).getByText("Hindi")).toBeTruthy();
  expect(within(group).getByText("3.4 s")).toBeTruthy();
  expect(within(group).getByText("2 takes")).toBeTruthy();
  expect(within(group).getByText("Approved")).toBeTruthy();
  expect(within(screen.getByRole("group", { name: "Scene s2" })).getByText("No take yet")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Continue to key frames" }) as HTMLButtonElement).disabled).toBe(true);
});

it("enables the footer once the stage is approved", async () => {
  setup(board([line("s1", { state: "approved" })], { stage: "VOICES_APPROVED" }));
  await screen.findByText("1 of 1 lines approved");
  expect((screen.getByRole("button", { name: "Continue to key frames" }) as HTMLButtonElement).disabled).toBe(false);
});

it("states: needs update, failed with retry, no voice, no dialogue", async () => {
  const calls = setup(
    board(
      [
        line("s1", { state: "stale" }),
        line("s2", { state: "failed", message: "boom" }),
        line("s3", { state: "no_voice", message: "Pick a voice for Tamatar", takes: [] }),
        line("s4", { state: "no_dialogue", text: "", takes: [] }),
      ],
    ),
  );
  await screen.findByText("Needs update");
  expect(screen.getByRole("button", { name: "Regenerate stale items" })).toBeTruthy();
  const failed = screen.getByRole("group", { name: "Scene s2" });
  expect(within(failed).getByText("Couldn't generate this line.")).toBeTruthy();
  await userEvent.click(within(failed).getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(calls.some((c) => c.path.endsWith("/voices:generate"))).toBe(true));
  expect(JSON.parse(calls.find((c) => c.path.endsWith("/voices:generate"))?.body ?? "{}")).toEqual({
    mode: "lines",
    lines: ["s2"],
  });
  expect(screen.getByText("Pick a voice for Tamatar")).toBeTruthy();
  expect(screen.getByText("No dialogue")).toBeTruthy();
});

it("takes select marks the active take and speed shows the readout", async () => {
  setup(board([line("s1", { speed: 1.25, pause_before: 0.5 })]));
  const group = await screen.findByRole("group", { name: "Scene s1" });
  expect(within(group).getByRole("option", { name: "Take 2 (3.1 s) - Active" })).toBeTruthy();
  expect(within(group).getByRole("option", { name: "Take 1 (3.1 s)" })).toBeTruthy();
  expect(within(group).getByLabelText("Speed value").textContent).toBe("1.25x");
  expect((within(group).getByLabelText("Pause before") as HTMLInputElement).value).toBe("0.5");
});

it("set-timing is sent when the speed changes", async () => {
  const calls = setup(board([line("s1")]));
  const group = await screen.findByRole("group", { name: "Scene s1" });
  fireEvent.change(within(group).getByLabelText("Speed"), { target: { value: "1.1" } });
  await waitFor(() => expect(calls.some((c) => c.path.endsWith("/s1:set-timing"))).toBe(true));
  expect(JSON.parse(calls[0]?.body ?? "{}")).toEqual({ speed: 1.1 });
});

it("shows the shot length after approval and the over-budget actions", async () => {
  setup(
    board([
      line("s1", { state: "approved", frames: 73, shot_length_s: 73 / 24 }),
      line("s2", { over_budget: { line_s: 4.2, budget_s: 3 } }),
    ]),
  );
  expect(await screen.findByText("Shot length: 73 frames (3.04 s)")).toBeTruthy();
  const g = screen.getByRole("group", { name: "Scene s2" });
  expect(within(g).getByText("This line is 4.2 s but the scene allows 3.0 s.")).toBeTruthy();
  for (const name of ["Speed up", "Shorten text", "Extend scene"]) {
    expect(within(g).getByRole("button", { name })).toBeTruthy();
  }
  await userEvent.click(within(g).getByRole("button", { name: "Shorten text" }));
  expect(await within(g).findByText("Shorter: Chhota vakya")).toBeTruthy();
});

it("recorded-voice characters upload recordings instead of making new takes", async () => {
  setup(board([line("s1", { speaker: "potato", speaker_name: "Aloo" })]));
  const g = await screen.findByRole("group", { name: "Scene s1" });
  expect(within(g).getByLabelText("Upload recording")).toBeTruthy();
  expect(within(g).queryByRole("button", { name: "New take" })).toBeNull();
});

it("shows job progress with elapsed seconds and Cancel", async () => {
  const job = {
    id: "j1",
    status: "running",
    message: "line 2 of 5",
    payload: { total: 5 },
    result: { completed: 1, total: 5, elapsed_s: 14 },
  } as unknown as VoiceBoardState["job"];
  setup(board([line("s1")], { job }));
  expect(await screen.findByText(/^Rendering line 2 of 5 - 14 s elapsed/)).toBeTruthy();
  expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
});

it("edit text and re-take saves the text and starts a new take", async () => {
  const calls = setup(board([line("s1")]));
  const g = await screen.findByRole("group", { name: "Scene s1" });
  await userEvent.click(within(g).getByRole("button", { name: "Edit text and re-take" }));
  const box = within(g).getByLabelText("Line text");
  await userEvent.clear(box);
  await userEvent.type(box, "Naya vakya");
  await userEvent.click(within(g).getByRole("button", { name: "Save and re-take" }));
  await waitFor(() => expect(calls.some((c) => c.path.endsWith("/voices:generate"))).toBe(true));
  expect(calls[0]?.path.endsWith("/s1:edit-text")).toBe(true);
  expect(JSON.parse(calls[0]?.body ?? "{}")).toEqual({ text: "Naya vakya" });
});
