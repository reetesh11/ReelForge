import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { at, FakeWebSocket, json, project, renderApp, stubFetch } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const list = (body: unknown) => (url: URL) => (url.pathname === "/api/v1/projects" ? json(body) : undefined);

describe("layout", () => {
  it("shows the main nav without library or brand kit links", async () => {
    stubFetch([list([])]);
    renderApp("/projects");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Projects" })).toBeTruthy();
    expect(within(nav).getByRole("link", { name: "Settings & status" })).toBeTruthy();
    expect(within(nav).queryByRole("link", { name: /cast/i })).toBeNull();
    expect(within(nav).queryByRole("link", { name: /brand/i })).toBeNull();
  });

  it("redirects / to the project list", async () => {
    stubFetch([list([])]);
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeTruthy();
  });

  it("shows Reconnecting... only while the socket is not connected", async () => {
    stubFetch([list([])]);
    renderApp("/projects");
    expect((await screen.findByRole("status")).textContent).toContain("Reconnecting...");
    FakeWebSocket.last.simulateOpen();
    await waitFor(() => expect(screen.queryByText("Reconnecting...")).toBeNull());
    FakeWebSocket.last.simulateClose();
    expect(await screen.findByText("Reconnecting...")).toBeTruthy();
  });

  it("is dark first", async () => {
    const { readFileSync } = await import("node:fs");
    const { resolve } = await import("node:path");
    const html = readFileSync(resolve(__dirname, "../../index.html"), "utf8");
    expect(html).toMatch(/<html[^>]*class="[^"]*\bdark\b/);
  });
});

describe("ProjectsPage", () => {
  it("shows skeleton rows while loading", async () => {
    stubFetch([() => new Promise<Response>(() => {})]);
    renderApp("/projects");
    expect(await screen.findAllByTestId("project-skeleton")).toHaveLength(3);
  });

  it("renders one row per project with title link, stage count and edited time", async () => {
    stubFetch([list([project(), project({ id: "01ARZ3NDEKTSV4RRFFQ69G5FAW", title: "Second reel", stages_approved: 0 })])]);
    renderApp("/projects");
    const ul = await screen.findByRole("list", { name: "Projects" });
    const items = within(ul).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(at(items, 0)).getByRole("link", { name: "Tomato tale" })).toBeTruthy();
    expect(within(at(items, 0)).getByText("1/6 stages approved")).toBeTruthy();
    expect(at(items, 0).querySelector("time")).not.toBeNull();
    expect(within(at(items, 1)).getByText("0/6 stages approved")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New project" })).toBeTruthy();
  });

  it("shows the empty state", async () => {
    stubFetch([list([])]);
    renderApp("/projects");
    expect(await screen.findByText("No projects yet.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "New project" })).toBeTruthy();
  });

  it("shows the error state and retries", async () => {
    let calls = 0;
    stubFetch([
      (url) => {
        if (url.pathname !== "/api/v1/projects") return undefined;
        calls += 1;
        return calls === 1 ? json({ detail: "boom" }, 500) : json([project()]);
      },
    ]);
    renderApp("/projects");
    expect(await screen.findByText("Couldn't load projects.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("link", { name: "Tomato tale" })).toBeTruthy();
  });

  it("creates a project through the form and refreshes the list", async () => {
    const posted: unknown[] = [];
    let created = false;
    stubFetch([
      async (url, init) => {
        if (url.pathname !== "/api/v1/projects") return undefined;
        if (init?.method === "POST") {
          const body = init.body ? JSON.parse(String(init.body)) : null;
          posted.push(body);
          created = true;
          return json(project({ title: "Brand new" }), 201);
        }
        return json(created ? [project({ title: "Brand new" })] : []);
      },
    ]);
    renderApp("/projects");
    fireEvent.click(await screen.findByRole("button", { name: "New project" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Project title" }), { target: { value: "Brand new" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("link", { name: "Brand new" })).toBeTruthy();
    expect(posted).toHaveLength(1);
  });
});
