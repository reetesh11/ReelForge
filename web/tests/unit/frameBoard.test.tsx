import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { Frame, FramesState } from "@/api/frames";
import { FrameBoard } from "@/frames/FrameBoard";

afterEach(() => vi.unstubAllGlobals());

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

function take(n: number, active: boolean) {
  return {
    id: `t${n}`,
    take_no: n,
    seed: n,
    active,
    approved: false,
    stale: false,
    source: "render" as const,
    image_url: `/media/t${n}`,
    inputs: ["m1"],
  };
}

function frame(sid: string, over: Partial<Frame> = {}): Frame {
  return {
    scene_id: sid,
    position: 1,
    characters: [{ key: "tomato", name: "Tamatar" }],
    master: { key: "tomato", name: "Tamatar", artifact_id: "m1" },
    framing: "medium",
    state: "ready",
    prompt: "A tomato waves",
    prompt_source: "llm",
    look_removed: false,
    takes: [take(1, false), take(2, true)],
    notes: {},
    continue_previous: false,
    job: null,
    ...over,
  };
}

function board(frames: Frame[], over: Partial<FramesState> = {}): FramesState {
  return {
    stage: "VOICES_APPROVED",
    approved_count: frames.filter((f) => f.state === "approved").length,
    total: frames.length,
    stale_count: frames.filter((f) => f.state === "stale").length,
    jobs: [],
    frames,
    ...over,
  };
}

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function setup(state: FramesState, handlers: { onBack?: () => void; onContinue?: () => void } = {}) {
  const calls: Array<{ method: string; path: string; body: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : null;
      const url = new URL(req ? req.url : String(input), "http://localhost");
      const method = req ? req.method : (init?.method ?? "GET");
      const body = req ? await req.clone().text() : String(init?.body ?? "");
      if (method !== "GET") calls.push({ method, path: url.pathname, body });
      if (url.pathname === `${API}/frames` && method === "GET") return reply(state);
      return reply({ id: "j1", type: "gen_frame", jobs: [], skipped: [], cancelled: 1 }, 202);
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <FrameBoard projectId={ID} {...handlers} />
    </QueryClientProvider>,
  );
  return calls;
}

it("shows the heading, counts, badges and the per-scene controls", async () => {
  setup(board([frame("s1", { state: "approved" }), frame("s2", { takes: [], state: "no_frame" })]));
  expect(await screen.findByRole("heading", { name: "Key frames" })).toBeTruthy();
  expect(screen.getByText("1 of 2 frames approved")).toBeTruthy();
  const list = screen.getByRole("list", { name: "Frames" });
  expect(within(list).getAllByRole("group")).toHaveLength(2);
  const s1 = screen.getByRole("group", { name: "Scene s1" });
  expect(within(s1).getByText("Approved")).toBeTruthy();
  expect(within(s1).getByRole("button", { name: "Regenerate" })).toBeTruthy();
  expect((within(s1).getByRole("button", { name: "Approve" }) as HTMLButtonElement).disabled).toBe(true);
  expect(within(s1).getByRole("combobox", { name: "Takes" })).toBeTruthy();
  const s2 = screen.getByRole("group", { name: "Scene s2" });
  expect(within(s2).getByText("No frame yet")).toBeTruthy();
  expect(within(s2).getByRole("button", { name: "Generate" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Regenerate stale items" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Cancel" })).toBeNull();
  expect((screen.getByRole("button", { name: "Continue to shots" }) as HTMLButtonElement).disabled).toBe(true);
});

it("shows stale, progress and cancel while jobs run, and enables the footer once approved", async () => {
  const job = {
    id: "j1",
    status: "running",
    payload: { scene_id: "s1", index: 2, total: 5 },
    started_at: new Date().toISOString(),
  };
  const calls = setup(
    board([frame("s1", { state: "stale" })], {
      stale_count: 1,
      jobs: [job as never],
      stage: "FRAMES_APPROVED",
    }),
  );
  expect(await screen.findByText(/^Generating frame 2 of 5 - \d+ s elapsed$/)).toBeTruthy();
  expect(screen.getByText("Needs update")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Continue to shots" }) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.getByRole("button", { name: "Regenerate stale items" })).toBeTruthy();
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/frames:cancel`)).toBe(true));
});

it("explains notes: second character, product, missing master, look removed, failure", async () => {
  setup(
    board([
      frame("s1", {
        notes: { second_character: { master_name: "Tamatar", other_name: "Aloo" }, product: "missing" },
        look_removed: true,
      }),
      frame("s2", { state: "failed", message: "boom", notes: { needs_master: "Aloo", product: "included" } }),
      frame("s3", { notes: { waiting_for_previous_shot: true, no_character: true }, state: "continue_previous" }),
    ]),
  );
  await screen.findByRole("heading", { name: "Key frames" });
  expect(
    screen.getByText(
      "Built from Tamatar's master. Aloo is described in the prompt, not copied. Use Upload replacement if the second character looks wrong.",
    ),
  ).toBeTruthy();
  expect(screen.getByText("Product image missing")).toBeTruthy();
  expect(screen.getByText("Product pack included")).toBeTruthy();
  expect(screen.getByText("The character description was removed from the prompt.")).toBeTruthy();
  expect(screen.getByText("Approve a master for Aloo in Cast first")).toBeTruthy();
  expect(screen.getByText("Couldn't generate this frame.")).toBeTruthy();
  expect(screen.getByText("boom")).toBeTruthy();
  expect(screen.getByText("Waiting for the previous shot to be rendered")).toBeTruthy();
  expect(screen.getByText("No character in this scene")).toBeTruthy();
  const s2 = screen.getByRole("group", { name: "Scene s2" });
  expect((within(s2).getByRole("button", { name: "Regenerate" }) as HTMLButtonElement).disabled).toBe(true);
  expect(within(s2).getByRole("button", { name: "Retry" })).toBeTruthy();
});

it("sends framing, prompt and generate requests", async () => {
  const calls = setup(board([frame("s1")]));
  const card = await screen.findByRole("group", { name: "Scene s1" });
  await userEvent.selectOptions(within(card).getByRole("combobox", { name: "Framing" }), "closeup");
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/frames/s1:set-framing`)).toBe(true));
  expect(JSON.parse(calls.find((c) => c.path.endsWith(":set-framing"))?.body ?? "{}")).toEqual({ framing: "closeup" });
  const prompt = within(card).getByRole("textbox", { name: "Frame prompt" });
  await userEvent.clear(prompt);
  await userEvent.type(prompt, "Plain");
  await userEvent.click(within(card).getByRole("button", { name: "Save and regenerate" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/frames/s1:save-prompt`)).toBe(true));
  expect(JSON.parse(calls.find((c) => c.path.endsWith(":save-prompt"))?.body ?? "{}")).toEqual({
    prompt: "Plain",
    regenerate: true,
  });
  await userEvent.click(within(card).getByRole("button", { name: "Regenerate" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/frames/s1:generate`)).toBe(true));
  await userEvent.click(screen.getByRole("button", { name: "Generate all frames" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/frames:generate`)).toBe(true));
});

it("calls the back and continue handlers", async () => {
  const onBack = vi.fn();
  const onContinue = vi.fn();
  setup(board([frame("s1", { state: "approved" })], { stage: "FRAMES_APPROVED" }), { onBack, onContinue });
  await userEvent.click(await screen.findByRole("button", { name: "Back to voices" }));
  await userEvent.click(screen.getByRole("button", { name: "Continue to shots" }));
  expect(onBack).toHaveBeenCalledTimes(1);
  expect(onContinue).toHaveBeenCalledTimes(1);
});
