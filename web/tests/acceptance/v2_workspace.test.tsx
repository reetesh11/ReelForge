import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket } from "./helpers";

const stagesModule = () => import("@/workspace/stages");

import { ID, KEYS, mount, sixStages } from "./v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

function byProject(name: string) {
  const v = BY_PROJECT[name];
  if (!v) throw new Error(`no fixture ${name}`);
  return v;
}
const panels = () => Array.from(document.querySelectorAll('[data-testid^="stage-panel-"]')).map((e) => e.getAttribute("data-testid"));
const loc = () => screen.getByTestId("probe-location").textContent;

// Project stage -> stages data with everything up to the landing stage unlocked.
const BY_PROJECT: Record<string, { states: string[]; unlocked: number; key: string }> = {
  DRAFT: { states: ["needs_review"], unlocked: 1, key: "story" },
  STORY_APPROVED: { states: ["approved", "needs_review"], unlocked: 2, key: "cast" },
  CAST_APPROVED: { states: ["approved", "approved", "needs_review"], unlocked: 3, key: "voices" },
  VOICES_APPROVED: { states: ["approved", "approved", "approved", "needs_review"], unlocked: 4, key: "frames" },
  FRAMES_APPROVED: { states: ["approved", "approved", "approved", "approved", "needs_review"], unlocked: 5, key: "shots" },
  SHOTS_APPROVED: { states: ["approved", "approved", "approved", "approved", "approved", "needs_review"], unlocked: 6, key: "assembly" },
  EXPORTED: { states: ["approved", "approved", "approved", "approved", "approved", "approved"], unlocked: 6, key: "assembly" },
};

describe("AC-2 stage rail links", () => {
  const stages = sixStages(["approved", "needs_review", "not_started", "rendering", "failed", "queued"], 2, { 3: 42 });

  it("six cells: unlocked ones link to ?stage=<key>, locked ones have no link, shown one is current", async () => {
    mount(`/projects/${ID}`, { stages });
    const ol = await screen.findByRole("list", { name: "Stages" });
    const items = within(ol).getAllByRole("listitem");
    expect(items).toHaveLength(6);
    items.forEach((li, i) => {
      const links = li.querySelectorAll("a");
      if (i < 2) {
        expect(links).toHaveLength(1);
        expect((links[0] as HTMLAnchorElement).getAttribute("href")).toMatch(new RegExp(`\\?stage=${KEYS[i]}$`));
        expect(li.getAttribute("aria-disabled")).toBeNull();
      } else {
        expect(links).toHaveLength(0);
        expect(li.getAttribute("aria-disabled")).toBe("true");
      }
    });
    const current = ol.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0]?.tagName).toBe("A");
    expect(current[0]?.getAttribute("href")).toMatch(/\?stage=cast$/);
  });

  it("current marker follows ?stage=", async () => {
    mount(`/projects/${ID}?stage=story`, { stages });
    const ol = await screen.findByRole("list", { name: "Stages" });
    const current = ol.querySelectorAll('[aria-current="step"]');
    expect(current).toHaveLength(1);
    expect(current[0]?.getAttribute("href")).toMatch(/\?stage=story$/);
  });

  it("each cell has a stage-name and a separate stage-state element (two lines)", async () => {
    mount(`/projects/${ID}`, { stages });
    const ol = await screen.findByRole("list", { name: "Stages" });
    expect(ol.classList.contains("stage-rail")).toBe(true);
    const items = within(ol).getAllByRole("listitem");
    const labels = ["Story", "Cast", "Voices", "Key frames", "Shots", "Assembly"];
    const states = ["Approved", "Needs review", "Not started", "Rendering 42%", "Failed", "Queued"];
    items.forEach((li, i) => {
      expect(li.classList.contains("stage-cell")).toBe(true);
      const name = li.querySelector('[data-testid="stage-name"]');
      const state = li.querySelector('[data-testid="stage-state"]');
      expect(name).not.toBeNull();
      expect(state).not.toBeNull();
      expect(name?.contains(state as Node)).toBe(false);
      expect(name?.textContent).toContain(labels[i]);
      expect(name?.getAttribute("title")).toBe(labels[i]);
      expect(state?.textContent?.trim()).toBe(states[i]);
    });
  });
});

describe("AC-3 landing stage shows only its panel", () => {
  for (const [projectStage, spec] of Object.entries(BY_PROJECT)) {
    it(`${projectStage} lands on ${spec.key}`, async () => {
      mount(`/projects/${ID}`, { projectStage, stages: sixStages(spec.states, spec.unlocked) });
      await screen.findByRole("list", { name: "Stages" });
      await waitFor(() => expect(panels()).toEqual([`stage-panel-${spec.key}`]));
      expect(loc()).toBe(`/projects/${ID}`);
    });
  }

  it("REEL_EXPORTED lands on assembly", async () => {
    mount(`/projects/${ID}`, { projectStage: "REEL_EXPORTED", stages: sixStages(byProject("EXPORTED").states, 6) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-assembly"]));
  });
});

describe("AC-4 ?stage= and legacy ?screen=", () => {
  it("?stage=cast shows only Cast", async () => {
    mount(`/projects/${ID}?stage=cast`, { projectStage: "VOICES_APPROVED", stages: sixStages(byProject("VOICES_APPROVED").states, 4) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    expect(screen.getByRole("heading", { name: "Cast" })).toBeTruthy();
  });

  it("?stage=voices shows only Voices", async () => {
    mount(`/projects/${ID}?stage=voices`, { projectStage: "VOICES_APPROVED", stages: sixStages(byProject("VOICES_APPROVED").states, 4) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-voices"]));
  });

  it("?screen=frames, shots, assembly and voices still work", async () => {
    const s = byProject("SHOTS_APPROVED");
    for (const [screenValue, key] of [["frames", "frames"], ["shots", "shots"], ["assembly", "assembly"], ["voices", "voices"]]) {
      const { unmount } = mount(`/projects/${ID}?screen=${screenValue}`, { projectStage: "SHOTS_APPROVED", stages: sixStages(s.states, 6) });
      await waitFor(() => expect(panels()).toEqual([`stage-panel-${key}`]));
      unmount();
      vi.unstubAllGlobals();
    }
  });

  it("stage wins over screen", async () => {
    mount(`/projects/${ID}?stage=story&screen=cast`, { stages: sixStages(["approved", "needs_review"], 2) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-story"]));
  });

  it("a locked stage falls back to the landing stage", async () => {
    mount(`/projects/${ID}?stage=shots`, { stages: sixStages(["approved", "needs_review"], 2) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    expect(document.querySelector('[aria-current="step"]')?.getAttribute("href")).toMatch(/\?stage=cast$/);
  });

  it("a locked ?screen= and an unknown value fall back too", async () => {
    const first = mount(`/projects/${ID}?screen=assembly`, { stages: sixStages(["approved", "needs_review"], 2) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    first.unmount();
    vi.unstubAllGlobals();
    mount(`/projects/${ID}?stage=nonsense`, { stages: sixStages(["approved", "needs_review"], 2) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
  });
});

describe("AC-5 client-side navigation", () => {
  it("clicking a stage link swaps the panel without reload and Back restores it", async () => {
    mount(`/projects/${ID}`, { stages: sixStages(["approved", "needs_review"], 2) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    const sockets = FakeWebSocket.instances.length;
    const user = userEvent.setup();
    const ol = screen.getByRole("list", { name: "Stages" });
    await user.click(within(ol).getAllByRole("link")[0] as HTMLElement);
    await waitFor(() => expect(panels()).toEqual(["stage-panel-story"]));
    expect(loc()).toBe(`/projects/${ID}?stage=story`);
    expect(FakeWebSocket.instances.length).toBe(sockets);
    await user.click(screen.getByTestId("probe-back"));
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    expect(loc()).toBe(`/projects/${ID}`);
  });

  it("Enter on a focused stage link navigates", async () => {
    mount(`/projects/${ID}`, { stages: sixStages(["approved", "needs_review"], 2) });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    const user = userEvent.setup();
    const link = within(screen.getByRole("list", { name: "Stages" })).getAllByRole("link")[0] as HTMLElement;
    link.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(panels()).toEqual(["stage-panel-story"]));
  });

  it("Continue buttons change the URL stage and keep their names", async () => {
    mount(`/projects/${ID}`, {
      projectStage: "VOICES_APPROVED",
      stages: sixStages(byProject("VOICES_APPROVED").states, 4),
      frames: {
        stage: "VOICES_APPROVED", approved_count: 1, total: 1, stale_count: 0, jobs: [],
        frames: [{ scene_id: "s1", position: 1, characters: [], master: null, framing: "medium", state: "approved", prompt: "p", prompt_source: "llm", look_removed: false, takes: [], notes: {}, continue_previous: false, job: null }],
      },
    });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-frames"]));
    fireEvent.click(await screen.findByRole("button", { name: "Back to voices" }));
    await waitFor(() => expect(panels()).toEqual(["stage-panel-voices"]));
    expect(loc()).toContain("stage=voices");
  });
});

describe("AC-6 next-up bar", () => {
  const stages = sixStages(["approved", "needs_review"], 2);

  it("is absent when the waiting stage is the shown one", async () => {
    mount(`/projects/${ID}`, { stages });
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    expect(screen.queryByTestId("next-up")).toBeNull();
    expect(screen.queryByRole("button", { name: "Go to Cast" })).toBeNull();
  });

  it("names the waiting stage and its button navigates there", async () => {
    mount(`/projects/${ID}?stage=story`, { stages });
    const bar = await screen.findByTestId("next-up");
    expect(bar.textContent).toContain("Cast needs review");
    const user = userEvent.setup();
    await user.click(within(bar).getByRole("button", { name: "Go to Cast" }));
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    expect(loc()).toContain("stage=cast");
    expect(screen.queryByTestId("next-up")).toBeNull();
  });

  it("is absent when every unlocked stage is approved", async () => {
    mount(`/projects/${ID}?stage=story`, { stages: sixStages(["approved", "approved"], 2) });
    await screen.findByRole("list", { name: "Stages" });
    expect(screen.queryByTestId("next-up")).toBeNull();
  });

  it("uses a failed stage's reason", async () => {
    mount(`/projects/${ID}?stage=story`, {
      projectStage: "VOICES_APPROVED",
      stages: sixStages(["approved", "approved", "approved", "failed"], 4),
    });
    const bar = await screen.findByTestId("next-up");
    expect(bar.textContent).toContain("Key frames failed");
    expect(within(bar).getByRole("button", { name: "Go to Key frames" })).toBeTruthy();
  });
});

describe("AC-7 header and progress", () => {
  it("shows breadcrumb, h1 title and N of 6 with a proportional bar", async () => {
    mount(`/projects/${ID}`, {
      projectStage: "FRAMES_APPROVED",
      stages: sixStages(["approved", "approved", "approved", "stale", "needs_review"], 5),
    });
    expect(await screen.findByRole("heading", { level: 1, name: "Tomato tale" })).toBeTruthy();
    const crumbs = screen.getByRole("navigation", { name: "Breadcrumb" });
    expect(within(crumbs).getByRole("link", { name: "Projects" }).getAttribute("href")).toBe("/projects");
    expect(crumbs.textContent).toContain("Project");
    expect(await screen.findByText("3 of 6 stages approved")).toBeTruthy();
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("3");
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("6");
    const fill = within(bar).getByTestId("progress-fill");
    expect(fill.style.width).toBe("50%");
  });

  it("shows 0 of 6 and a zero-width fill when nothing is approved", async () => {
    mount(`/projects/${ID}`, { projectStage: "DRAFT", stages: sixStages(["needs_review"], 1) });
    expect(await screen.findByText("0 of 6 stages approved")).toBeTruthy();
    expect(within(screen.getByRole("progressbar")).getByTestId("progress-fill").style.width).toBe("0%");
  });

  it("shows no readout, rail or next-up while stages failed to load", async () => {
    mount(`/projects/${ID}`, { stages: "fail" });
    expect(await screen.findByRole("heading", { level: 1, name: "Tomato tale" })).toBeTruthy();
    await waitFor(() => expect(panels()).toEqual(["stage-panel-cast"]));
    expect(screen.queryByText(/of 6 stages approved/)).toBeNull();
    expect(screen.queryByRole("list", { name: "Stages" })).toBeNull();
    expect(screen.queryByTestId("next-up")).toBeNull();
  });
});

type Info = Array<{ key: string; label: string; state: string; progress: number | null; locked: boolean }>;
const stages = (states: string[], unlocked: number): Info => sixStages(states, unlocked) as unknown as Info;
const q = (s: string) => new URLSearchParams(s);


describe("AC-3 helpers: landingStage", () => {
  it("lists the six keys in order", async () => {
    const { STAGE_KEYS } = await stagesModule();
    expect([...STAGE_KEYS]).toEqual(["story", "cast", "voices", "frames", "shots", "assembly"]);
  });

  it("landingStage follows the R6 table", async () => {
    const { landingStage } = await stagesModule();
    const table: Array<[string, string]> = [
      ["DRAFT", "story"],
      ["STORY_APPROVED", "cast"],
      ["CAST_APPROVED", "voices"],
      ["VOICES_APPROVED", "frames"],
      ["FRAMES_APPROVED", "shots"],
      ["SHOTS_APPROVED", "assembly"],
      ["REEL_EXPORTED", "assembly"],
      ["EXPORTED", "assembly"],
    ];
    for (const [project, key] of table) {
      expect(landingStage(project as Parameters<typeof landingStage>[0])).toBe(key);
    }
  });
});

describe("AC-4 helpers: resolveStage", () => {
  it("stage wins over screen, aliases work, locked and unknown fall back", async () => {
    const { resolveStage } = await stagesModule();
    const open = stages(["approved", "approved", "approved", "needs_review"], 4);
    expect(resolveStage(q("stage=cast"), "VOICES_APPROVED", open)).toBe("cast");
    expect(resolveStage(q("screen=voices"), "VOICES_APPROVED", open)).toBe("voices");
    expect(resolveStage(q("stage=story&screen=cast"), "VOICES_APPROVED", open)).toBe("story");
    expect(resolveStage(q("stage=shots"), "VOICES_APPROVED", open)).toBe("frames");
    expect(resolveStage(q("stage=bogus"), "VOICES_APPROVED", open)).toBe("frames");
    expect(resolveStage(q(""), "VOICES_APPROVED", open)).toBe("frames");
    expect(resolveStage(q("stage=shots"), "VOICES_APPROVED", undefined)).toBe("shots");
    expect(resolveStage(q("stage=bogus"), "VOICES_APPROVED", undefined)).toBe("frames");
  });
});

describe("AC-6 helpers: waitingStage and waitingReason", () => {
  it("waitingStage prefers attention states, then first not approved, else null", async () => {
    const { waitingStage } = await stagesModule();
    expect(waitingStage(stages(["approved", "needs_review"], 3))?.key).toBe("cast");
    expect(waitingStage(stages(["approved", "not_started", "failed"], 3))?.key).toBe("voices");
    expect(waitingStage(stages(["approved", "not_started", "stale"], 3))?.key).toBe("voices");
    expect(waitingStage(stages(["approved", "not_started"], 2))?.key).toBe("cast");
    expect(waitingStage(stages(["approved", "approved"], 2))).toBeNull();
    expect(waitingStage(stages(["approved", "approved", "failed"], 2))).toBeNull();
  });

  it("waitingReason wording", async () => {
    const { waitingReason } = await stagesModule();
    const [s, c, v, f, sh] = stages(["needs_review", "failed", "stale", "not_started", "queued"], 6);
    expect(waitingReason(s as Info[number])).toBe("Story needs review");
    expect(waitingReason(c as Info[number])).toBe("Cast failed");
    expect(waitingReason(v as Info[number])).toBe("Voices is stale");
    expect(waitingReason(f as Info[number])).toBe("Key frames not started");
    expect(waitingReason(sh as Info[number])).toBe("Shots queued");
  });
});

describe("AC-7 helpers: approvedCount", () => {
  it("counts approved stages", async () => {
    const { approvedCount } = await stagesModule();
    expect(approvedCount(stages(["approved", "approved", "stale", "approved"], 4))).toBe(3);
    expect(approvedCount(stages([], 1))).toBe(0);
  });
});
