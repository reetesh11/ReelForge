import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket } from "./helpers";
import { castBody, ID, mount } from "./v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

async function openCard(cast: unknown) {
  mount(`/projects/${ID}`, { cast });
  const card = await screen.findByTestId("cast-card");
  await within(card).findByRole("button", { name: "Approve this one" });
  return card;
}

const tiles = (card: HTMLElement) => Array.from(card.querySelectorAll("button.tile")) as HTMLButtonElement[];

describe("AC-13a cast icon buttons and tile selection", () => {
  it("every action is a button with its old name, a title and an svg", async () => {
    const card = await openCard(castBody());
    for (const name of [
      "Regenerate 4 more",
      "Edit look text and regenerate",
      "Refine selected (img2img)",
      "Upload my own image",
      "Use from library",
    ]) {
      const b = within(card).getByRole("button", { name });
      expect(b.getAttribute("title")).toBe(name);
      expect(b.querySelector("svg")).not.toBeNull();
    }
    const approve = within(card).getByRole("button", { name: "Approve this one" });
    expect(approve.querySelector("svg")).not.toBeNull();
    expect(approve.textContent?.trim()).toBe("Approve");
  });

  it("the only visible-text buttons are Approve (and the age save)", async () => {
    const card = await openCard(castBody());
    const texts = within(card)
      .getAllByRole("button")
      .map((b) => (b.textContent ?? "").trim())
      .filter((t) => t !== "" && t !== "Save age");
    expect(texts).toEqual(["Approve"]);
  });

  it("an empty card shows Generate candidates as its only visible-text button", async () => {
    mount(`/projects/${ID}`, { cast: castBody({}, { state: "empty", candidates: [] }) });
    const card = await screen.findByTestId("cast-card");
    const gen = await within(card).findByRole("button", { name: "Generate candidates" });
    expect(gen.classList.contains("btn-primary")).toBe(true);
    const texts = within(card)
      .getAllByRole("button")
      .map((b) => (b.textContent ?? "").trim())
      .filter((t) => t !== "" && t !== "Save age");
    expect(texts).toEqual(["Generate candidates"]);
  });

  it("approved cards use icon buttons for Change approval and Replace from library", async () => {
    mount(`/projects/${ID}`, {
      cast: castBody({ approved_count: 1 }, { approved: true, state: "approved", master_artifact_id: "m1" }),
    });
    const card = await screen.findByTestId("cast-card");
    for (const name of ["Change approval", "Replace from library"]) {
      const b = await within(card).findByRole("button", { name });
      expect(b.getAttribute("title")).toBe(name);
      expect(b.querySelector("svg")).not.toBeNull();
    }
  });

  it("clicking a tile selects it and shows one check badge on that tile", async () => {
    const card = await openCard(castBody());
    const [first, second] = tiles(card);
    expect(first).toBeTruthy();
    expect(card.querySelectorAll('[data-testid="check-badge"]')).toHaveLength(0);
    await userEvent.setup().click(first as HTMLElement);
    await waitFor(() => expect(card.querySelectorAll('[data-testid="check-badge"]')).toHaveLength(1));
    expect(first?.querySelector('[data-testid="check-badge"]')).not.toBeNull();
    expect(second?.querySelector('[data-testid="check-badge"]')).toBeNull();
  });
});

describe("AC-13 selected tile and Approve gating", () => {
  it("keeps aria-pressed and the selected class, and enables Approve only after a selection", async () => {
    const card = await openCard(castBody());
    const approve = () => within(card).getByRole("button", { name: "Approve this one" }) as HTMLButtonElement;
    const [first, second] = tiles(card);
    expect(tiles(card)).toHaveLength(2);
    expect(first?.getAttribute("aria-pressed")).toBe("false");
    expect(second?.getAttribute("aria-pressed")).toBe("false");
    expect(approve().disabled).toBe(true);
    await userEvent.setup().click(second as HTMLElement);
    await waitFor(() => expect(second?.getAttribute("aria-pressed")).toBe("true"));
    expect(first?.getAttribute("aria-pressed")).toBe("false");
    expect(approve().disabled).toBe(false);
  });
});
