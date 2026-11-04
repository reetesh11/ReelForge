import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ShotBoard } from "@/shots/ShotBoard";
import { json, stubFetch } from "../acceptance/helpers";

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";

afterEach(() => vi.unstubAllGlobals());

it("gives the shot card the player's frame-step controls and keeps the shot video label", async () => {
  const take = {
    id: "t1", take_no: 1, seed: 1, active: true, approved: false, stale: false, source: "render",
    quality: "draft", video_url: "/media/t1", last_frame_id: null, inputs: [],
  };
  const shot = {
    scene_id: "s1", position: 1, shot_type: "talking", shot_type_auto: "talking", quality: "draft",
    width: 320, height: 576, frames: 81, shot_length_s: 3.375, motion_prompt: "x", state: "ready",
    blockers: [], frame_url: null, takes: [take], job: null,
  };
  const board = {
    stage: "FRAMES_APPROVED", engine: { ok: true, message: "" }, approved_count: 0, total: 1, stale_count: 0,
    shots: [shot],
    queue: { paused: false, rows: [], total_shots: 0, total_s: 0, total_text: "", running: null },
  };
  stubFetch([(url) => (url.pathname === `/api/v1/projects/${ID}/shots` ? json(board) : undefined)]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <ShotBoard projectId={ID} />
    </QueryClientProvider>,
  );
  const card = await screen.findByRole("group", { name: "Scene s1" });
  const video = within(card).getByLabelText("Shot video") as HTMLVideoElement;
  expect(video.loop).toBe(true);
  for (const name of ["Previous frame", "Next frame", "Play", "Safe-zone overlay"]) {
    expect(within(card).getByRole("button", { name })).toBeTruthy();
  }
});
