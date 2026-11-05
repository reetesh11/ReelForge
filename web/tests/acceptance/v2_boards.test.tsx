import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket } from "./helpers";
import { frame, framesBody, ID, mount, shot, shotsBody, sixStages, voiceLine, voicesBody, type Scenario } from "./v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const A = ["approved", "approved", "approved", "approved", "approved"];
const VOICES: Scenario = { projectStage: "CAST_APPROVED", stages: sixStages([...A.slice(0, 2), "needs_review"], 3) };
const FRAMES: Scenario = { projectStage: "VOICES_APPROVED", stages: sixStages([...A.slice(0, 3), "needs_review"], 4) };
const SHOTS: Scenario = { projectStage: "FRAMES_APPROVED", stages: sixStages([...A.slice(0, 4), "needs_review"], 5) };

function chips(p: HTMLElement) {
  return within(p).getAllByTestId("state-chip").map((c) => ({
    text: c.textContent?.trim(),
    attention: c.closest("li")?.getAttribute("data-attention"),
  }));
}

describe("AC-14 status strip and state chips", () => {
  it("Voices", async () => {
    mount(`/projects/${ID}`, {
      ...VOICES,
      voices: voicesBody([
        voiceLine("s1", { state: "approved" }),
        voiceLine("s2", { state: "stale" }),
        voiceLine("s3", { state: "no_take", takes: [], duration_s: null }),
      ]),
    });
    const p = await screen.findByTestId("stage-panel-voices");
    const strip = await within(p).findByTestId("status-strip");
    expect(strip.textContent).toContain("1 of 3 lines approved");
    expect(strip.textContent).toContain("1 line has no take yet");
    expect(chips(p)).toEqual([
      { text: "Approved", attention: null },
      { text: "Needs update", attention: "true" },
      { text: "No take yet", attention: null },
    ]);
  });

  it("Key frames", async () => {
    mount(`/projects/${ID}`, {
      ...FRAMES,
      frames: framesBody([
        frame("s1", { state: "approved" }),
        frame("s2", { state: "stale" }),
        frame("s3", { state: "no_frame", takes: [] }),
      ]),
    });
    const p = await screen.findByTestId("stage-panel-frames");
    const strip = await within(p).findByTestId("status-strip");
    expect(strip.textContent).toContain("1 of 3 frames approved");
    expect(chips(p)).toEqual([
      { text: "Approved", attention: null },
      { text: "Needs update", attention: "true" },
      { text: "No frame yet", attention: null },
    ]);
  });

  it("Shots", async () => {
    mount(`/projects/${ID}`, {
      ...SHOTS,
      shots: shotsBody([
        shot("s1", { state: "approved" }),
        shot("s2", { state: "stale" }),
        shot("s3", { state: "no_shot", takes: [] }),
      ]),
    });
    const p = await screen.findByTestId("stage-panel-shots");
    const strip = await within(p).findByTestId("status-strip");
    expect(strip.textContent).toContain("1 of 3 shots approved");
    expect(chips(p)).toEqual([
      { text: "Approved", attention: null },
      { text: "Needs update", attention: "true" },
      { text: "No shot yet", attention: null },
    ]);
  });
});
