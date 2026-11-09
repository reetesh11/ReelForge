import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { at, FakeWebSocket, json, project, renderApp, stubFetch } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

describe("AC-15 project cards", () => {
  it("shows a six-segment mini rail with titles and N/6 text, keeping the old hooks", async () => {
    stubFetch([
      (url) =>
        url.pathname === "/api/v1/projects"
          ? json([project({ stages_approved: 2 }), project({ id: "01ARZ3NDEKTSV4RRFFQ69G5FAW", title: "Second", stages_approved: 0 })])
          : undefined,
    ]);
    renderApp("/projects");
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeTruthy();
    const ul = await screen.findByRole("list", { name: "Projects" });
    const items = within(ul).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    const first = at(items, 0);
    expect(within(first).getByText("2/6 stages approved")).toBeTruthy();
    const rail = within(first).getByTestId("mini-rail");
    const segs = within(rail).getAllByTestId("mini-rail-segment");
    expect(segs).toHaveLength(6);
    segs.forEach((s) => {
      expect(["approved", "waiting", "not_started"]).toContain(s.getAttribute("data-state"));
      expect((s.getAttribute("title") ?? "").length).toBeGreaterThan(0);
    });
    expect(segs.filter((s) => s.getAttribute("data-state") === "approved")).toHaveLength(2);
    const second = within(within(at(items, 1)).getByTestId("mini-rail")).getAllByTestId("mini-rail-segment");
    expect(second.filter((s) => s.getAttribute("data-state") === "approved")).toHaveLength(0);
    expect(within(at(items, 1)).getByText("0/6 stages approved")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New project" }).classList.contains("btn-primary")).toBe(true);
  });

  it("keeps the empty text and the skeleton test ids", async () => {
    stubFetch([() => new Promise<Response>(() => {})]);
    renderApp("/projects");
    expect(await screen.findAllByTestId("project-skeleton")).toHaveLength(3);
    vi.unstubAllGlobals();
    stubFetch([(url) => (url.pathname === "/api/v1/projects" ? json([]) : undefined)]);
    renderApp("/projects");
    expect(await screen.findByText("No projects yet.")).toBeTruthy();
  });
});
