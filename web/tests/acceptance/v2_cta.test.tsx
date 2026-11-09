import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket } from "./helpers";
import {
  assemblyBody, castBody, frame, framesBody, ID, mount, shot, shotsBody, sixStages, voiceLine, voicesBody,
  type Scenario,
} from "./v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const cls = (el: HTMLElement) => Array.from(el.classList);
const btn = (root: HTMLElement, name: string) => within(root).getByRole("button", { name }) as HTMLButtonElement;
const panel = async (key: string) => screen.findByTestId(`stage-panel-${key}`);
const ctas = (root: HTMLElement) => root.querySelectorAll(".btn-cta");
const waitBtn = async (root: HTMLElement, name: string) => (await within(root).findByRole("button", { name })) as HTMLButtonElement;

const A = ["approved", "approved", "approved", "approved", "approved"];
const VOICES: Scenario = { projectStage: "CAST_APPROVED", stages: sixStages([...A.slice(0, 2), "needs_review"], 3) };
const FRAMES: Scenario = { projectStage: "VOICES_APPROVED", stages: sixStages([...A.slice(0, 3), "needs_review"], 4) };
const SHOTS: Scenario = { projectStage: "FRAMES_APPROVED", stages: sixStages([...A.slice(0, 4), "needs_review"], 5) };
const ASSEMBLY: Scenario = { projectStage: "SHOTS_APPROVED", stages: sixStages([...A, "needs_review"], 6) };
const DRAFT: Scenario = { projectStage: "DRAFT", stages: sixStages(["needs_review"], 1), storyApproved: false };

describe("AC-8 CTA names, class and preconditions", () => {
  it("Story: Approve story is the CTA and is disabled while the draft is dirty", async () => {
    mount(`/projects/${ID}`, DRAFT);
    const p = await panel("story");
    const approve = await waitBtn(p, "Approve story");
    expect(cls(approve)).toContain("btn-cta");
    expect(approve.disabled).toBe(false);
    const scene = await screen.findByLabelText("Scene s2");
    fireEvent.change(within(scene).getByRole("textbox", { name: "Action" }), { target: { value: "Aloo dances" } });
    await waitFor(() => expect(btn(p, "Approve story").disabled).toBe(true));
    expect(btn(p, "Approve story").title).toBe("Save your changes first");
  });

  it("Story: after approval Approve story is secondary and the banner is a notice", async () => {
    mount(`/projects/${ID}?stage=story`, { projectStage: "STORY_APPROVED", stages: sixStages(["approved", "needs_review"], 2), storyApproved: true });
    const p = await panel("story");
    const approve = await waitBtn(p, "Approve story");
    expect(cls(approve)).toContain("btn-secondary");
    expect(cls(approve)).not.toContain("btn-cta");
    const banner = within(p).getByText("Story approved. Editing it will mark dependent items for update.");
    expect(banner.closest(".notice")).not.toBeNull();
  });

  it("Story: Delete buttons are danger", async () => {
    mount(`/projects/${ID}`, DRAFT);
    const p = await panel("story");
    await screen.findByLabelText("Scene s2");
    const deletes = within(p).getAllByRole("button", { name: /^Delete/ });
    expect(deletes.length).toBeGreaterThan(0);
    deletes.forEach((d) => expect(cls(d)).toContain("btn-danger"));
  });

  it("Cast: Approve this one is the CTA, disabled until a tile is selected", async () => {
    mount(`/projects/${ID}`, { cast: castBody() });
    const card = await screen.findByTestId("cast-card");
    const approve = await waitBtn(card, "Approve this one");
    expect(cls(approve)).toContain("btn-cta");
    expect(approve.disabled).toBe(true);
    await userEvent.setup().click(card.querySelector("button.tile") as HTMLElement);
    await waitFor(() => expect(btn(card, "Approve this one").disabled).toBe(false));
  });

  it("Voices: Continue to key frames is the CTA, disabled until voices are approved", async () => {
    mount(`/projects/${ID}`, { ...VOICES, voices: voicesBody([voiceLine("s1")]) });
    const go = await waitBtn(await panel("voices"), "Continue to key frames");
    expect(cls(go)).toContain("btn-cta");
    expect(go.disabled).toBe(true);
  });

  it("Voices: enabled when the board stage is VOICES_APPROVED", async () => {
    mount(`/projects/${ID}`, { ...VOICES, voices: voicesBody([voiceLine("s1", { state: "approved" })], { stage: "VOICES_APPROVED" }) });
    const go = await waitBtn(await panel("voices"), "Continue to key frames");
    expect(cls(go)).toContain("btn-cta");
    expect(go.disabled).toBe(false);
  });

  it("Key frames: Continue to shots is the CTA, disabled until frames are approved", async () => {
    mount(`/projects/${ID}`, { ...FRAMES });
    const go = await waitBtn(await panel("frames"), "Continue to shots");
    expect(cls(go)).toContain("btn-cta");
    expect(go.disabled).toBe(true);
  });

  it("Key frames: enabled when frames are approved", async () => {
    mount(`/projects/${ID}`, { ...FRAMES, frames: framesBody([frame("s1", { state: "approved" })], { stage: "FRAMES_APPROVED" }) });
    const go = await waitBtn(await panel("frames"), "Continue to shots");
    expect(cls(go)).toContain("btn-cta");
    expect(go.disabled).toBe(false);
  });

  it("Shots: Continue to assembly is the CTA, disabled until shots are approved", async () => {
    mount(`/projects/${ID}`, { ...SHOTS });
    const go = await waitBtn(await panel("shots"), "Continue to assembly");
    expect(cls(go)).toContain("btn-cta");
    expect(go.disabled).toBe(true);
  });

  it("Shots: enabled when shots are approved", async () => {
    mount(`/projects/${ID}`, { ...SHOTS, shots: shotsBody([shot("s1", { state: "approved" })], { stage: "SHOTS_APPROVED" }) });
    const go = await waitBtn(await panel("shots"), "Continue to assembly");
    expect(cls(go)).toContain("btn-cta");
    expect(go.disabled).toBe(false);
  });

  it("Assembly: Export final is the CTA and is enabled unless blocked", async () => {
    mount(`/projects/${ID}`, { ...ASSEMBLY, assembly: assemblyBody() });
    const go = await waitBtn(await panel("assembly"), "Export final");
    expect(cls(go)).toContain("btn-cta");
    expect(go.disabled).toBe(false);
  });

  it("Assembly: Export final is disabled when blocked", async () => {
    mount(`/projects/${ID}`, { ...ASSEMBLY, assembly: assemblyBody({ blocked_reason: "Approve all shots before exporting." }) });
    const go = await waitBtn(await panel("assembly"), "Export final");
    expect(cls(go)).toContain("btn-cta");
    expect(go.disabled).toBe(true);
  });
});

describe("AC-9 one CTA per panel, generate actions are primary", () => {
  it("Story panel has at most one CTA", async () => {
    mount(`/projects/${ID}`, DRAFT);
    const p = await panel("story");
    await waitBtn(p, "Approve story");
    expect(ctas(p).length).toBe(1);
  });

  it("Cast has at most one CTA per card and Generate candidates is primary", async () => {
    const body = castBody({ total: 3 });
    const first = (body.characters as unknown[])[0] as Record<string, unknown>;
    body.characters = [
      first,
      { ...first, key: "potato", name: "Aloo" },
      { ...first, key: "empty", name: "Blank", state: "empty", candidates: [] },
    ];
    mount(`/projects/${ID}`, { cast: body });
    await waitFor(() => expect(screen.getAllByTestId("cast-card")).toHaveLength(3));
    const cards = screen.getAllByTestId("cast-card");
    cards.forEach((c) => {
      expect(c.classList.contains("card")).toBe(true);
      expect(c.querySelectorAll(".btn-cta").length).toBeLessThanOrEqual(1);
    });
    const gen = btn(cards[2] as HTMLElement, "Generate candidates");
    expect(cls(gen)).toContain("btn-primary");
    expect(cls(gen)).not.toContain("btn-cta");
  });

  it("Voices: one CTA, Generate all lines is primary", async () => {
    mount(`/projects/${ID}`, { ...VOICES });
    const p = await panel("voices");
    expect(cls(await waitBtn(p, "Generate all lines"))).toContain("btn-primary");
    expect(ctas(p).length).toBe(1);
  });

  it("Key frames: one CTA, Generate all frames is primary", async () => {
    mount(`/projects/${ID}`, { ...FRAMES });
    const p = await panel("frames");
    expect(cls(await waitBtn(p, "Generate all frames"))).toContain("btn-primary");
    expect(ctas(p).length).toBe(1);
  });

  it("Shots: one CTA, Render all is primary", async () => {
    mount(`/projects/${ID}`, { ...SHOTS });
    const p = await panel("shots");
    expect(cls(await waitBtn(p, "Render all"))).toContain("btn-primary");
    expect(ctas(p).length).toBe(1);
  });

  it("Assembly: one CTA, Rebuild preview is primary", async () => {
    mount(`/projects/${ID}`, { ...ASSEMBLY });
    const p = await panel("assembly");
    expect(cls(await waitBtn(p, "Rebuild preview"))).toContain("btn-primary");
    expect(ctas(p).length).toBe(1);
  });
});
