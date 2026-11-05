import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FakeWebSocket } from "../acceptance/helpers";
import { castBody, ID, mount } from "../acceptance/v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

it("shows the Cast heading and status strip counts", async () => {
  mount(`/projects/${ID}`, { cast: castBody() });
  expect(await screen.findByRole("heading", { name: "Cast" })).toBeTruthy();
  const strip = await screen.findByTestId("status-strip");
  expect(strip.textContent).toContain("0 of 1 characters approved");
});

it("closes the Enlarge dialog with Escape and returns focus to its button", async () => {
  mount(`/projects/${ID}`, { cast: castBody() });
  const card = await screen.findByTestId("cast-card");
  const opener = await within(card).findByRole("button", { name: "Enlarge seed 5" });
  opener.focus();
  fireEvent.click(opener);
  expect(await screen.findByRole("dialog")).toBeTruthy();
  fireEvent.keyDown(document, { key: "Escape" });
  await vi.waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  expect(document.activeElement).toBe(opener);
});
