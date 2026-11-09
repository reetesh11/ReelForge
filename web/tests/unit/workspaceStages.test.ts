import { expect, it } from "vitest";
import type { StageInfo } from "@/components/StageStepper";
import { approvedCount, landingStage, resolveStage, waitingReason, waitingStage } from "@/workspace/stages";

const info = (key: string, state: StageInfo["state"], locked = false, progress: number | null = null): StageInfo =>
  ({ key, label: key, state, locked, progress }) as StageInfo;

it("maps the project stage to a landing stage", () => {
  expect(landingStage("DRAFT")).toBe("story");
  expect(landingStage("EXPORTED")).toBe("assembly");
});

it("stage param wins over screen and locked values fall back", () => {
  const open = [info("story", "approved"), info("cast", "needs_review"), info("voices", "not_started", true)];
  expect(resolveStage(new URLSearchParams("stage=story&screen=cast"), "STORY_APPROVED", open)).toBe("story");
  expect(resolveStage(new URLSearchParams("screen=cast"), "STORY_APPROVED", open)).toBe("cast");
  expect(resolveStage(new URLSearchParams("stage=voices"), "STORY_APPROVED", open)).toBe("cast");
  expect(resolveStage(new URLSearchParams("stage=nope"), "STORY_APPROVED", undefined)).toBe("cast");
  expect(resolveStage(new URLSearchParams("stage=voices"), "STORY_APPROVED", undefined)).toBe("voices");
});

it("finds the waiting stage and its reason", () => {
  expect(waitingStage([info("story", "approved"), info("cast", "not_started"), info("voices", "failed")])?.key).toBe("voices");
  expect(waitingStage([info("story", "approved")])).toBeNull();
  expect(waitingReason(info("Cast", "needs_review"))).toBe("Cast needs review");
  expect(waitingReason(info("Shots", "rendering", false, 5))).toBe("Shots rendering 5%");
});

it("counts approved stages", () => {
  expect(approvedCount([info("a", "approved"), info("b", "stale")])).toBe(1);
});
