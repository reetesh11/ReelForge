import { expect, it } from "vitest";
import { estimateLength } from "@/story/length";

it("shows estimate against target", () => {
  expect(estimateLength([3, 3, 3, 2.5], 12)).toBe("Estimated length: 11.5 s of 12 s target");
});

it("mentions scenes without duration", () => {
  expect(estimateLength([3, null, undefined], 12)).toBe(
    "Estimated length: 3 s of 12 s target (2 scenes have no duration yet)",
  );
  expect(estimateLength([3, null], 12)).toContain("(1 scene has no duration yet)");
});

it("flags over target", () => {
  expect(estimateLength([7, 6.5], 12)).toBe("Over target by 1.5 s");
});
