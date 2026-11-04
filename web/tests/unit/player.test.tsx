import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it } from "vitest";
import { Player } from "@/player/Player";

let time = 0;

beforeEach(() => {
  time = 0;
  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    configurable: true,
    get: () => time,
    set: (v: number) => {
      time = v;
    },
  });
  Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: () => Promise.resolve() });
  Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: () => {} });
});

it("steps by 1/24 s with a custom frame rate respected", async () => {
  render(<Player src="/media/a" label="Clip" fps={10} />);
  await userEvent.click(screen.getByRole("button", { name: "Next frame" }));
  expect(time).toBeCloseTo(0.1, 6);
  await userEvent.click(screen.getByRole("button", { name: "Previous frame" }));
  expect(time).toBeCloseTo(0, 6);
  await userEvent.click(screen.getByRole("button", { name: "Previous frame" }));
  expect(time).toBe(0);
});

it("toggles Play and Pause, and Mute and Unmute", async () => {
  render(<Player src="/media/a" label="Clip" />);
  await userEvent.click(screen.getByRole("button", { name: "Play" }));
  expect(screen.getByRole("button", { name: "Pause" })).toBeTruthy();
  await userEvent.click(screen.getByRole("button", { name: "Mute" }));
  expect(screen.getByRole("button", { name: "Unmute" })).toBeTruthy();
});

it("changes speed on the video", async () => {
  render(<Player src="/media/a" label="Clip" />);
  await userEvent.selectOptions(screen.getByRole("combobox", { name: "Speed" }), "2x");
  expect((screen.getByLabelText("Clip") as HTMLVideoElement).playbackRate).toBe(2);
});

it("can hide its controls and shows the overlay when asked to", () => {
  render(<Player src="/media/a" label="Clip" controls={false} showSafeZone />);
  expect(screen.queryByRole("button", { name: "Play" })).toBeNull();
  expect(screen.getByTestId("safe-zone-overlay")).toBeTruthy();
});

it("reloads the source on Retry", async () => {
  render(<Player src="/media/a" label="Clip" />);
  fireEvent.error(screen.getByLabelText("Clip"));
  expect(screen.getByText(/Couldn't load this video\./)).toBeTruthy();
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(screen.getByText("Loading video...")).toBeTruthy();
});

it("can drop the group role for crowded screens", () => {
  render(<Player src="/media/a" label="Clip" grouped={false} />);
  expect(screen.queryByRole("group")).toBeNull();
});
