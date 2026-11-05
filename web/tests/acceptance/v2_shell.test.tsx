import { screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket, json, renderApp, stubFetch } from "./helpers";
import { API, ID, mount } from "./v2_helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const list = (body: unknown) => (url: URL) => (url.pathname === "/api/v1/projects" ? json(body) : undefined);

describe("AC-1 sidebar", () => {
  it("lists the three links in order with hrefs, brand inside the nav, active marked", async () => {
    stubFetch([list([])]);
    renderApp("/settings");
    const nav = await screen.findByRole("navigation", { name: "Main" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((l) => l.textContent)).toEqual(["Projects", "Settings & status", "Library"]);
    expect(links.map((l) => l.getAttribute("href"))).toEqual(["/projects", "/settings", "/library"]);
    expect(links.map((l) => l.getAttribute("aria-current"))).toEqual([null, "page", null]);
    expect(nav.textContent).toContain("ReelForge");
  });

  it("redirects / to /projects", async () => {
    stubFetch([list([])]);
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Projects" })).toBeTruthy();
    const nav = screen.getByRole("navigation", { name: "Main" });
    expect(within(nav).getByRole("link", { name: "Projects" }).getAttribute("aria-current")).toBe("page");
  });
});

describe("AC-23 banner and page-state messages", () => {
  it("keeps the reconnect banner role and text", async () => {
    stubFetch([list([])]);
    renderApp("/projects");
    const banner = await screen.findByRole("status");
    expect(banner.textContent).toContain("Reconnecting...");
  });

  it("Project not found. is a state-message", async () => {
    stubFetch([() => json({ detail: "project not found" }, 404)]);
    renderApp(`/projects/${ID}`);
    const el = await screen.findByText("Project not found.");
    expect(el.closest(".state-message")).not.toBeNull();
  });

  it("Couldn't load this project. is a state-message", async () => {
    stubFetch([() => json({ detail: "boom" }, 500)]);
    renderApp(`/projects/${ID}`);
    const el = await screen.findByText("Couldn't load this project.");
    expect(el.closest(".state-message")).not.toBeNull();
  });

  it("Loading... is a state-message while the project loads", async () => {
    stubFetch([() => new Promise<Response>(() => {})]);
    renderApp(`/projects/${ID}`);
    const el = await screen.findByText("Loading...");
    expect(el.closest(".state-message")).not.toBeNull();
  });

  it("Couldn't load the story. is a state-message", async () => {
    mount(`/projects/${ID}`, {
      projectStage: "DRAFT",
      extra: [(url, init) => (url.pathname === `${API}/story` && init?.method === "GET" ? json({ detail: "boom" }, 500) : undefined)],
    });
    const el = await screen.findByText("Couldn't load the story.");
    expect(el.closest(".state-message")).not.toBeNull();
  });

  it("This stage arrives in a later milestone. is a state-message", async () => {
    mount(`/projects/${ID}`, {
      projectStage: "DRAFT",
      extra: [(url, init) => (url.pathname === `${API}/story` && init?.method === "GET" ? json({ detail: "Not Found" }, 404) : undefined)],
    });
    const el = await screen.findByText("This stage arrives in a later milestone.");
    expect(el.closest(".state-message")).not.toBeNull();
  });
});
