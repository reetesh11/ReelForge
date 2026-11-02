import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { FakeWebSocket, json, project, renderApp, stage, stubFetch, type Route } from "../acceptance/helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;
const YAML = `version: 1
title: "T"
language: english
characters:
  tomato:
    name: "Tamatar"
    look: "round red tomato"
scenes:
  - id: s1
    action: "a"
    duration: 3.0
  - id: s2
    action: "b"
    duration: 3.0
  - id: s3
    action: "c"
    duration: 3.0
  - id: s4
    action: "d"
    duration: 3.0
`;

const cand = (seed: number) => ({
  id: `c${seed}`,
  kind: "generated",
  prompt: `prompt ${seed}`,
  seed,
  model: "model-x",
  model_key: "image",
  image_url: `/media/c${seed}`,
  width: 576,
  height: 1024,
});

function character(over: Record<string, unknown> = {}) {
  return {
    key: "tomato",
    name: "Tamatar",
    aliases: ["Tom"],
    look: "round red tomato",
    bible_line: "round red tomato",
    bible_source: "llm",
    state: "ready",
    candidates: [cand(5), cand(6)],
    approved: false,
    voice_reference: "",
    ...over,
  };
}

function cast(chars: unknown[], approved = 0) {
  return {
    stage: "STORY_APPROVED",
    approved_count: approved,
    total: chars.length,
    image_backend: { kind: "mock", reachable: true, port: 7860, mflux_available: false },
    characters: chars,
  };
}

function setup(body: unknown, extra: Route[] = []) {
  const stages = ["Story", "Cast", "Voices", "Key frames", "Shots", "Assembly"].map((l, i) =>
    stage(l.toLowerCase(), l, i === 0 ? "approved" : "not_started", null, i > 1),
  );
  const version = { id: "v1", version: 1, is_current: true, approved_at: "2026-11-01T10:00:00Z", created_at: "2026-11-01T10:00:00Z" };
  stubFetch([
    ...extra,
    (url) => (url.pathname === API ? json(project()) : undefined),
    (url) => (url.pathname === `${API}/stages` ? json({ stages }) : undefined),
    (url) => (url.pathname === `${API}/story` ? json({ ...version, yaml_text: YAML }) : undefined),
    (url) => (url.pathname === `${API}/story/versions` ? json([version]) : undefined),
    (url) => (url.pathname === `${API}/cast` ? json(body) : undefined),
    (url) => (url.pathname === "/api/v1/library/characters" ? json([]) : undefined),
    (url) => (url.pathname === "/api/v1/story/schema" ? json({ type: "object" }) : undefined),
  ]);
  renderApp(`/projects/${ID}`);
}

it("shows the empty state with a Generate button, aliases and a not-approved badge", async () => {
  setup(cast([character({ state: "empty", candidates: [] })]));
  const row = await screen.findByLabelText("Character: Tamatar");
  expect(within(row).getByText("No candidates yet")).toBeTruthy();
  expect(within(row).getByRole("button", { name: "Generate candidates" })).toBeTruthy();
  expect(within(row).getByText("Not approved")).toBeTruthy();
  expect(await screen.findByText("0 of 1 characters approved")).toBeTruthy();
});

it("shows progress with a Cancel button while generating", async () => {
  const job = { id: "j1" };
  setup(cast([character({ state: "generating", job_id: job.id, progress: { completed: 1, total: 4, elapsed_s: 12.4, message: "image 2 of 4" } })]));
  const row = await screen.findByLabelText("Character: Tamatar");
  expect(within(row).getByText(/^Generating image 2 of 4 - 1\d s elapsed$/)).toBeTruthy();
  expect(within(row).getByRole("button", { name: "Cancel" })).toBeTruthy();
});

it("shows the stopped and failed states", async () => {
  setup(cast([character({ state: "stopped", progress: { completed: 2, total: 4, elapsed_s: 5, message: "" } })]));
  expect(await screen.findByText("Stopped after 2 of 4 images")).toBeTruthy();
});

it("shows the failure message with Retry", async () => {
  setup(cast([character({ state: "failed", error: "boom happened" })]));
  const row = await screen.findByLabelText("Character: Tamatar");
  expect(within(row).getByText("Couldn't generate images.")).toBeTruthy();
  expect(within(row).getByText("boom happened")).toBeTruthy();
  expect(within(row).getByRole("button", { name: "Retry" })).toBeTruthy();
});

it("shows the approved master, library note and variant message with the change button", async () => {
  setup(
    cast(
      [
        character({
          state: "approved",
          approved: true,
          master_artifact_id: "m1",
          library_character_id: "L1",
          variant_of_library_id: "L0",
        }),
      ],
      1,
    ),
  );
  const row = await screen.findByLabelText("Character: Tamatar");
  expect(within(row).getByText("Approved")).toBeTruthy();
  expect(within(row).getByText("This changes a library character, so a copy was made.")).toBeTruthy();
  expect(within(row).getByText(/^From library: /)).toBeTruthy();
  expect(within(row).getByRole("button", { name: "Change approval" })).toBeTruthy();
  expect(within(row).getByRole("button", { name: "Replace from library" })).toBeTruthy();
});

it("keeps Approve and Refine disabled until a candidate is selected, and enlarges a tile", async () => {
  setup(cast([character()]));
  const row = await screen.findByLabelText("Character: Tamatar");
  const user = userEvent.setup();
  const approve = within(row).getByRole("button", { name: "Approve this one" }) as HTMLButtonElement;
  const refine = within(row).getByRole("button", { name: "Refine selected (img2img)" }) as HTMLButtonElement;
  expect(approve.disabled).toBe(true);
  expect(refine.disabled).toBe(true);
  expect(within(row).getByLabelText("What small change?")).toBeTruthy();
  await user.click(within(row).getByRole("radio", { name: "Select candidate seed 6" }));
  expect(approve.disabled).toBe(false);
  expect(refine.disabled).toBe(false);
  await user.click(within(row).getByRole("button", { name: "Enlarge seed 5" }));
  const dialog = await screen.findByRole("dialog");
  expect(dialog.textContent).toContain("prompt 5");
  expect(dialog.textContent).toContain("model-x");
});

it("shows the server message when an upload is rejected", async () => {
  const upload: Route = (url, init) =>
    url.pathname === `${API}/cast/tomato:upload` && init?.method === "POST"
      ? json({ detail: "That file isn't a PNG or JPEG image." }, 415)
      : undefined;
  setup(cast([character()]), [upload]);
  const row = await screen.findByLabelText("Character: Tamatar");
  const user = userEvent.setup({ applyAccept: false });
  await user.upload(within(row).getByLabelText("Upload my own image"), new File(["x"], "x.png", { type: "image/png" }));
  await waitFor(() => expect(within(row).getByRole("alert").textContent).toBe("That file isn't a PNG or JPEG image."));
});

it("renders nothing when the cast request fails", async () => {
  setup(null);
  await screen.findByRole("heading", { name: "Tomato tale" });
  expect(screen.queryByLabelText("Cast")).toBeNull();
});
