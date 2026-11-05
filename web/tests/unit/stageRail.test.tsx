import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { StageStepper, type StageInfo } from "@/components/StageStepper";

const st = (key: string, label: string, over: Partial<StageInfo> = {}): StageInfo => ({
  key, label, state: "not_started", progress: null, locked: false, ...over,
});

it("links unlocked cells, marks the current one and leaves locked cells without a link", () => {
  const onSelect = vi.fn();
  render(
    <StageStepper
      current="cast"
      onSelect={onSelect}
      stages={[st("story", "Story"), st("cast", "Cast"), st("voices", "Voices", { locked: true })]}
    />,
  );
  const links = screen.getAllByRole("link");
  expect(links).toHaveLength(2);
  expect(links.map((l) => l.getAttribute("aria-current"))).toEqual([null, "step"]);
  fireEvent.click(links[0] as HTMLElement);
  expect(onSelect).toHaveBeenCalledWith("story");
});

it("shows a mini bar only while rendering with progress", () => {
  const { container } = render(
    <StageStepper stages={[st("frames", "Key frames", { state: "rendering", progress: 40 })]} />,
  );
  expect(container.querySelector(".stage-mini-bar")).not.toBeNull();
  expect(screen.getByText("Rendering 40%")).toBeTruthy();
});
