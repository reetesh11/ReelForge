import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import type { Queue } from "@/api/shots";
import { QueuePanel } from "@/shots/QueuePanel";

afterEach(() => vi.unstubAllGlobals());

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

const row = (n: number, sid: string, over: Record<string, unknown> = {}) => ({
  job_id: `j${n}`,
  scene_id: sid,
  position: n,
  shot_type: "talking" as const,
  quality: "draft" as const,
  width: 320,
  height: 576,
  status: "queued" as const,
  estimate_s: 180,
  estimate_text: "about 3 min",
  can_move: true,
  ...over,
});

function setup(queue: Queue) {
  const calls: Array<{ path: string; body: string }> = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : null;
      const url = new URL(req ? req.url : String(input), "http://localhost");
      calls.push({ path: url.pathname, body: req ? await req.clone().text() : String(init?.body ?? "") });
      return new Response(JSON.stringify(queue), { status: 200, headers: { "Content-Type": "application/json" } });
    }),
  );
  const result = render(
    <QueryClientProvider client={new QueryClient()}>
      <QueuePanel projectId={ID} queue={queue} />
    </QueryClientProvider>,
  );
  return { calls, ...result };
}

const base: Queue = {
  paused: false,
  rows: [
    row(1, "s1", { status: "running", can_move: false }),
    row(2, "s2"),
    row(3, "s3", { shot_type: "action", quality: "final" }),
  ],
  total_shots: 3,
  total_s: 540,
  total_text: "3 shots - about 9 min - keep the Mac plugged in",
  running: { scene_id: "s1", index: 1, total: 3, elapsed_s: 12 },
};

it("renders nothing without rows", () => {
  setup({ ...base, rows: [], running: null });
  expect(screen.queryByRole("region", { name: "Render queue" })).toBeNull();
});

it("shows the total, rows, running status and per-row controls", () => {
  setup(base);
  const panel = screen.getByRole("region", { name: "Render queue" });
  expect(within(panel).getByText("3 shots - about 9 min - keep the Mac plugged in")).toBeTruthy();
  expect(within(panel).getByText("1. s1 - Talking - Draft - about 3 min")).toBeTruthy();
  expect(within(panel).getByText("3. s3 - Action - Final - about 3 min")).toBeTruthy();
  expect(within(panel).getByText(/^Rendering shot 1 of 3 - \d+ s elapsed$/)).toBeTruthy();
  const running = within(panel).getByText("1. s1 - Talking - Draft - about 3 min").closest("li") as HTMLElement;
  expect((within(running).getByRole("button", { name: "Move down" }) as HTMLButtonElement).disabled).toBe(true);
  expect((within(running).getByRole("button", { name: "Remove" }) as HTMLButtonElement).disabled).toBe(true);
  const second = within(panel).getByText("2. s2 - Talking - Draft - about 3 min").closest("li") as HTMLElement;
  expect((within(second).getByRole("button", { name: "Move up" }) as HTMLButtonElement).disabled).toBe(true);
});

it("moves, removes, pauses and cancels", async () => {
  const { calls } = setup(base);
  const panel = screen.getByRole("region", { name: "Render queue" });
  const third = within(panel).getByText("3. s3 - Action - Final - about 3 min").closest("li") as HTMLElement;
  await userEvent.click(within(third).getByRole("button", { name: "Move up" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots/queue:move`)).toBe(true));
  expect(JSON.parse(calls.find((c) => c.path.endsWith("queue:move"))?.body ?? "{}")).toEqual({
    job_id: "j3",
    direction: "up",
  });
  await userEvent.click(within(third).getByRole("button", { name: "Remove" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots/s3:dequeue`)).toBe(true));
  await userEvent.click(within(panel).getByRole("button", { name: "Pause" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots/queue:pause`)).toBe(true));
  await userEvent.click(within(panel).getByRole("button", { name: "Cancel" }));
  await waitFor(() => expect(calls.some((c) => c.path === `${API}/shots/queue:cancel`)).toBe(true));
});

it("offers Resume while paused", () => {
  setup({ ...base, paused: true });
  expect(screen.getByRole("button", { name: "Resume" })).toBeTruthy();
  expect(screen.queryByRole("button", { name: "Pause" })).toBeNull();
});
