import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { Queue, Shot, ShotsState } from "@/api/shots";
import { ShotBoard } from "@/shots/ShotBoard";

afterEach(() => vi.unstubAllGlobals());

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

const take = (n: number, active: boolean) => ({
  id: `t${n}`,
  take_no: n,
  seed: n,
  active,
  approved: false,
  stale: false,
  source: "render" as const,
  quality: "draft" as const,
  video_url: `/media/t${n}`,
  last_frame_id: `l${n}`,
  inputs: [],
});

function shot(sid: string, over: Partial<Shot> = {}): Shot {
  return {
    scene_id: sid,
    position: 1,
    shot_type: "talking",
    shot_type_auto: "talking",
    quality: "draft",
    width: 320,
    height: 576,
    frames: 81,
    shot_length_s: 3.375,
    motion_prompt: "slow push in",
    state: "ready",
    blockers: [],
    frame_url: "/media/f1",
    takes: [take(1, false), take(2, true)],
    job: null,
    ...over,
  };
}

const emptyQueue: Queue = { paused: false, rows: [], total_shots: 0, total_s: 0, total_text: "", running: null };

function board(shots: Shot[], over: Partial<ShotsState> = {}): ShotsState {
  return {
    stage: "FRAMES_APPROVED",
    engine: { ok: true, message: "" },
    approved_count: shots.filter((s) => s.state === "approved").length,
    total: shots.length,
    stale_count: shots.filter((s) => s.state === "stale").length,
    shots,
    queue: emptyQueue,
    ...over,
  };
}

const reply = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

function setup(state: ShotsState, onBack?: () => void) {
  const calls: Array<{ method: string; path: string; body: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : null;
      const url = new URL(req ? req.url : String(input), "http://localhost");
      const method = req ? req.method : (init?.method ?? "GET");
      const body = req ? await req.clone().text() : String(init?.body ?? "");
      if (method !== "GET") calls.push({ method, path: url.pathname, body });
      if (url.pathname === `${API}/shots` && method === "GET") return reply(state);
      return reply({ id: "j1", jobs: [], skipped: [] }, 202);
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ShotBoard projectId={ID} onBack={onBack} />
    </QueryClientProvider>,
  );
  return calls;
}

it("shows header facts, controls and a looping video once a take exists", async () => {
  setup(board([shot("s1"), shot("s2", { takes: [], state: "no_shot", shot_type: "action" })]));
  expect(await screen.findByRole("heading", { name: "Shots" })).toBeTruthy();
  expect(screen.getByText("0 of 2 shots approved")).toBeTruthy();
  const list = screen.getByRole("list", { name: "Shot cards" });
  expect(within(list).getAllByRole("group")).toHaveLength(2);
  const s1 = screen.getByRole("group", { name: "Scene s1" });
  expect(within(s1).getAllByText("Talking").length).toBeGreaterThan(0);
  expect(within(s1).getAllByText("Draft").length).toBeGreaterThan(0);
  expect(within(s1).getByText("81 frames (3.38 s)")).toBeTruthy();
  expect(within(s1).getByLabelText("Shot video")).toBeTruthy();
  expect(within(s1).getByRole("combobox", { name: "Shot type" })).toBeTruthy();
  expect(within(s1).getByRole("combobox", { name: "Quality" })).toBeTruthy();
  expect(within(s1).getByRole("textbox", { name: "Motion prompt" })).toBeTruthy();
  for (const name of ["Save prompt", "Save and re-render", "Render", "Play", "Approve", "Re-roll", "Compare takes"]) {
    expect(within(s1).getByRole("button", { name })).toBeTruthy();
  }
  const s2 = screen.getByRole("group", { name: "Scene s2" });
  expect(within(s2).getByText("No shot yet")).toBeTruthy();
  expect(within(s2).queryByLabelText("Shot video")).toBeNull();
  expect((screen.getByRole("button", { name: "Continue to assembly" }) as HTMLButtonElement).disabled).toBe(true);
});

it("shows blocker notices and switches an unapproved voice to Action", async () => {
  const calls = setup(
    board([
      shot("s1", { takes: [], state: "no_shot", blockers: ["frame_not_approved", "voice_not_approved"] }),
      shot("s2", { takes: [], state: "no_shot", blockers: ["waiting_previous"] }),
    ]),
  );
  await screen.findByRole("heading", { name: "Shots" });
  expect(screen.getByText("Approve the key frame first")).toBeTruthy();
  expect(screen.getByText("Approve the voice take first")).toBeTruthy();
  expect(screen.getByText("Waiting for the previous shot")).toBeTruthy();
  const s1 = screen.getByRole("group", { name: "Scene s1" });
  expect((within(s1).getByRole("button", { name: "Render" }) as HTMLButtonElement).disabled).toBe(true);
  await userEvent.click(within(s1).getByRole("button", { name: "Switch to Action" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots/s1:set-type`)).toBe(true));
});

it("explains out-of-memory and other failures", async () => {
  const calls = setup(
    board([
      shot("s1", { state: "failed", takes: [], oom: true, can_retry_draft: true, message: "Killed, likely out of memory." }),
      shot("s2", { state: "failed", takes: [], oom: true, message: "Killed, likely out of memory." }),
      shot("s3", { state: "failed", takes: [], message: "ltx-2-mlx failed: bad frames" }),
    ]),
  );
  await screen.findByRole("heading", { name: "Shots" });
  const s1 = screen.getByRole("group", { name: "Scene s1" });
  expect(within(s1).getByText("Killed, likely out of memory.")).toBeTruthy();
  await userEvent.click(within(s1).getByRole("button", { name: "Retry at Draft size" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots/s1:retry-draft`)).toBe(true));
  const s2 = screen.getByRole("group", { name: "Scene s2" });
  expect(within(s2).queryByRole("button", { name: "Retry at Draft size" })).toBeNull();
  expect(within(s2).getByText("Close other apps and try again.")).toBeTruthy();
  const s3 = screen.getByRole("group", { name: "Scene s3" });
  expect(within(s3).getByText("Couldn't render this shot.")).toBeTruthy();
  expect(within(s3).getByText("ltx-2-mlx failed: bad frames")).toBeTruthy();
  await userEvent.click(within(s3).getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots/s3:render`)).toBe(true));
});

it("disables rendering and says so when the video engine check fails", async () => {
  setup(
    board([shot("s1", { takes: [], state: "no_shot" })], {
      engine: { ok: false, message: "Video engine check failed - see Settings & status" },
    }),
  );
  expect(await screen.findByText("Video engine check failed - see Settings & status")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Render all" }) as HTMLButtonElement).disabled).toBe(true);
  const s1 = screen.getByRole("group", { name: "Scene s1" });
  expect((within(s1).getByRole("button", { name: "Render" }) as HTMLButtonElement).disabled).toBe(true);
});

it("compares two takes side by side and makes one active", async () => {
  const calls = setup(board([shot("s1")]));
  const s1 = await screen.findByRole("group", { name: "Scene s1" });
  await userEvent.click(within(s1).getByRole("button", { name: "Compare takes" }));
  const dialog = await screen.findByRole("dialog");
  expect(within(dialog).getAllByRole("button", { name: "Make active" })).toHaveLength(2);
  await userEvent.click(within(dialog).getAllByRole("button", { name: "Make active" }).at(1) as HTMLElement);
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots/s1:select-take`)).toBe(true));
});

it("renders all, goes back, and enables the footer when approved", async () => {
  const onBack = vi.fn();
  const calls = setup(board([shot("s1", { state: "approved" })], { stage: "SHOTS_APPROVED" }), onBack);
  await screen.findByRole("heading", { name: "Shots" });
  expect((screen.getByRole("button", { name: "Continue to assembly" }) as HTMLButtonElement).disabled).toBe(false);
  await userEvent.click(screen.getByRole("button", { name: "Render all" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots:render-all`)).toBe(true));
  await userEvent.click(screen.getByRole("button", { name: "Back to key frames" }));
  expect(onBack).toHaveBeenCalledTimes(1);
});
