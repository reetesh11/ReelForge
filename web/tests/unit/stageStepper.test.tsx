import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { StageStepper, badgeText, type StageInfo } from "@/components/StageStepper";

const stage = (over: Partial<StageInfo>): StageInfo => ({
  key: "frames",
  label: "Key frames",
  state: "not_started",
  progress: null,
  locked: false,
  ...over,
});

it("formats badges", () => {
  expect(badgeText(stage({ state: "rendering", progress: 42 }))).toBe("Rendering 42%");
  expect(badgeText(stage({ state: "needs_review" }))).toBe("Needs review");
  expect(badgeText(stage({ state: "stale" }))).toBe("Stale");
});

it("marks locked stages aria-disabled", () => {
  render(<StageStepper stages={[stage({ key: "a", label: "A" }), stage({ key: "b", label: "B", locked: true })]} />);
  const items = within(screen.getByRole("list", { name: "Stages" })).getAllByRole("listitem");
  expect(items.map((i) => i.getAttribute("aria-disabled"))).toEqual([null, "true"]);
});
