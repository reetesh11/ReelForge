import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { at, FakeWebSocket, json, project, renderApp, stage, stubFetch } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const SIX = [
  stage("story", "Story", "approved", null, false),
  stage("cast", "Cast", "needs_review", null, false),
  stage("voices", "Voices", "not_started", null, true),
  stage("frames", "Key frames", "rendering", 42, true),
  stage("shots", "Shots", "failed", null, true),
  stage("assembly", "Assembly", "queued", null, true),
];

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";

function routesFor(stages: unknown[]) {
  return [
    (url: URL) => (url.pathname === `/api/v1/projects/${ID}` ? json(project()) : undefined),
    (url: URL) => (url.pathname === `/api/v1/projects/${ID}/stages` ? json({ stages }) : undefined),
  ];
}

describe("StageStepper", () => {
  it("renders six ordered stages with badges and disabled locked stages", async () => {
    stubFetch(routesFor(SIX));
    renderApp(`/projects/${ID}`);
    const ol = await screen.findByRole("list", { name: "Stages" });
    expect(ol.tagName).toBe("OL");
    const items = within(ol).getAllByRole("listitem");
    expect(items).toHaveLength(6);
    const text = items.map((i) => i.textContent ?? "");
    ["Story", "Cast", "Voices", "Key frames", "Shots", "Assembly"].forEach((l, i) => expect(at(text, i)).toContain(l));
    ["Approved", "Needs review", "Not started", "Rendering 42%", "Failed", "Queued"].forEach((b, i) =>
      expect(at(text, i)).toContain(b),
    );
    expect(items.map((i) => i.getAttribute("aria-disabled"))).toEqual([null, null, "true", "true", "true", "true"]);
  });

  it("shows Stale", async () => {
    stubFetch(routesFor([stage("story", "Story", "stale", null, false), ...SIX.slice(1)]));
    renderApp(`/projects/${ID}`);
    const ol = await screen.findByRole("list", { name: "Stages" });
    expect(at(within(ol).getAllByRole("listitem"), 0).textContent).toContain("Stale");
  });
});

describe("ProjectPage", () => {
  const routes = [
    (url: URL) => (url.pathname === "/api/v1/projects/01ARZ3NDEKTSV4RRFFQ69G5FAV" ? json(project()) : undefined),
    (url: URL) =>
      url.pathname === "/api/v1/projects/01ARZ3NDEKTSV4RRFFQ69G5FAV/stages" ? json({ stages: SIX }) : undefined,
  ];

  it("shows title, stepper and the placeholder body", async () => {
    stubFetch(routes);
    renderApp("/projects/01ARZ3NDEKTSV4RRFFQ69G5FAV");
    expect(await screen.findByRole("heading", { name: "Tomato tale" })).toBeTruthy();
    const ol = await screen.findByRole("list", { name: "Stages" });
    expect(within(ol).getAllByRole("listitem")).toHaveLength(6);
    expect(screen.getByText("This stage arrives in a later milestone.")).toBeTruthy();
  });

  it("shows Project not found. for an unknown id", async () => {
    stubFetch([() => json({ detail: "project not found" }, 404)]);
    renderApp("/projects/01ARZ3NDEKTSV4RRFFQ69G5FAX");
    expect(await screen.findByText("Project not found.")).toBeTruthy();
  });
});
