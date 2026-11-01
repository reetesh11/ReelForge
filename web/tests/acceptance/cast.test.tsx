import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket, json, project, renderApp, stage, stubFetch } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

const YAML_TEXT = `version: 1
title: "Tale"
language: english
style: "3D cartoon"
aspect: "9:16"
fps: 24
target_seconds: 12
characters:
  tomato:
    name: "Tamatar"
    look: "round red tomato"
scenes:
  - id: s1
    action: "Tamatar waves"
    duration: 3.0
  - id: s2
    action: "Tamatar smiles"
    duration: 3.0
  - id: s3
    action: "Tamatar jumps"
    duration: 3.0
  - id: s4
    action: "Tamatar bows"
    duration: 3.0
`;

function castBody(over: Record<string, unknown> = {}, backend: Record<string, unknown> = {}) {
  return {
    stage: "STORY_APPROVED",
    approved_count: 0,
    total: 1,
    image_backend: { kind: "mock", reachable: true, port: 7860, mflux_available: false, ...backend },
    characters: [
      {
        key: "tomato",
        name: "Tamatar",
        aliases: [],
        look: "round red tomato",
        bible_line: "round red tomato, plain background",
        bible_source: "llm",
        state: "ready",
        candidates: [
          { id: "a1", kind: "generated", prompt: "p", seed: 5, model: "m", model_key: "image", image_url: "/media/a1", width: 576, height: 1024 },
          { id: "a2", kind: "generated", prompt: "p", seed: 6, model: "m", model_key: "image", image_url: "/media/a2", width: 576, height: 1024 },
        ],
        approved: false,
        voice_reference: "",
      },
    ],
    ...over,
  };
}

function routes(cast: unknown, extra: Array<(url: URL, init?: RequestInit) => Response | undefined> = []) {
  const stages = ["Story", "Cast", "Voices", "Key frames", "Shots", "Assembly"].map((l, i) =>
    stage(l.toLowerCase(), l, i === 0 ? "approved" : "not_started", null, i > 1),
  );
  const version = { id: "v1", version: 1, is_current: true, approved_at: "2026-11-01T10:00:00Z", created_at: "2026-11-01T10:00:00Z" };
  return [
    ...extra,
    (url: URL) => (url.pathname === API ? json(project()) : undefined),
    (url: URL) => (url.pathname === `${API}/stages` ? json({ stages }) : undefined),
    (url: URL) => (url.pathname === `${API}/story` ? json({ ...version, yaml_text: YAML_TEXT }) : undefined),
    (url: URL) => (url.pathname === `${API}/story/versions` ? json([version]) : undefined),
    (url: URL) => (url.pathname === `${API}/cast` ? json(cast) : undefined),
    (url: URL) =>
      url.pathname === "/api/v1/story/schema" ? json({ type: "object", additionalProperties: false }) : undefined,
  ];
}

describe("Cast screen", () => {
  it("shows the unreachable panel with Retry and setup steps, without mflux when not configured", async () => {
    stubFetch(routes(castBody({}, { kind: "draw_things", reachable: false })));
    renderApp(`/projects/${ID}`);
    const section = await screen.findByLabelText("Cast");
    expect(await within(section).findByText("Draw Things isn't reachable on port 7860")).toBeTruthy();
    expect(within(section).getByRole("button", { name: "Retry" })).toBeTruthy();
    const steps = within(section).getAllByRole("listitem").map((li) => li.textContent);
    expect(steps).toContain("Install Draw Things from the Mac App Store.");
    expect(steps).toContain("Click Retry.");
    expect(section.textContent ?? "").not.toContain("mflux");
    expect(within(section).queryByRole("button", { name: "Generate candidates" })).toBeNull();
  });

  it("offers mflux only when it is available", async () => {
    stubFetch(routes(castBody({}, { kind: "draw_things", reachable: false, mflux_available: true })));
    renderApp(`/projects/${ID}`);
    const section = await screen.findByLabelText("Cast");
    expect(await within(section).findByRole("button", { name: "Use mflux instead" })).toBeTruthy();
  });

  it("shows the licence banner and a confirmation dialog before approving, and approves anyway", async () => {
    const posted: string[] = [];
    const warning = "Image model licence: Non-Commercial - not for commercial use. See u.";
    const approveRoute = (url: URL, init?: RequestInit) => {
      if (url.pathname === `${API}/cast/tomato:approve` && init?.method === "POST") {
        posted.push(url.pathname);
        return json({ project_stage: "CAST_APPROVED", approved_count: 1, total: 1, character: {} });
      }
      return undefined;
    };
    stubFetch(routes(castBody({ licence_warning: warning }), [approveRoute]));
    renderApp(`/projects/${ID}`);
    const section = await screen.findByLabelText("Cast");
    const banner = await within(section).findByRole("status");
    expect(banner.textContent).toContain(warning);
    const user = userEvent.setup();
    await user.click(within(section).getByRole("radio", { name: "Select candidate seed 5" }));
    await user.click(within(section).getByRole("button", { name: "Approve this one" }));
    const dialog = await screen.findByRole("dialog");
    expect(dialog.textContent).toContain(warning);
    expect(posted).toEqual([]);
    await user.click(within(dialog).getByRole("button", { name: "Approve anyway" }));
    await waitFor(() => expect(posted).toHaveLength(1));
  });

  it("approves directly, without a dialog, when the licence is permissive", async () => {
    const posted: string[] = [];
    const approveRoute = (url: URL, init?: RequestInit) => {
      if (url.pathname === `${API}/cast/tomato:approve` && init?.method === "POST") {
        posted.push(url.pathname);
        return json({ project_stage: "CAST_APPROVED", approved_count: 1, total: 1, character: {} });
      }
      return undefined;
    };
    stubFetch(routes(castBody(), [approveRoute]));
    renderApp(`/projects/${ID}`);
    const section = await screen.findByLabelText("Cast");
    const user = userEvent.setup();
    await user.click(await within(section).findByRole("radio", { name: "Select candidate seed 6" }));
    await user.click(within(section).getByRole("button", { name: "Approve this one" }));
    await waitFor(() => expect(posted).toHaveLength(1));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(within(section).queryByRole("status")).toBeNull();
  });
});

describe("Settings status panel licence row", () => {
  it("shows an amber image licence row only when /health carries the warning", async () => {
    const text = "Image model licence: Non-Commercial - not for commercial use. See u.";
    stubFetch([(url) => (url.pathname === "/health" ? json({ status: "ok", checks: [], image_licence_warning: text }) : undefined)]);
    renderApp("/settings");
    const row = await screen.findByLabelText("Image model licence: amber");
    expect(row.textContent).toContain(text);
  });

  it("has no licence row without the key", async () => {
    stubFetch([(url) => (url.pathname === "/health" ? json({ status: "ok", checks: [] }) : undefined)]);
    renderApp("/settings");
    await screen.findByRole("heading", { name: "Settings & status" });
    expect(screen.queryByLabelText("Image model licence: amber")).toBeNull();
  });
});
