import { expect, it } from "vitest";
import { miniRail } from "@/components/ProjectCard";

it("derives approved, one waiting, then not started", () => {
  expect(miniRail(2).map((s) => s.state)).toEqual(["approved", "approved", "waiting", "not_started", "not_started", "not_started"]);
  expect(miniRail(0)[0]?.state).toBe("waiting");
});

it("has no waiting segment once all six are approved", () => {
  expect(miniRail(6).every((s) => s.state === "approved")).toBe(true);
});
