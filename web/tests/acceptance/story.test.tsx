import { fireEvent, screen, waitFor, within } from "@testing-library/react";
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
    look: "round red tomato, big eyes, leaf hat, gold sherwani"
scenes:
  - id: s1
    setting: "A kitchen"
    action: "Tamatar waves"
    framing: wide
    duration: 3.0
  - id: s2
    action: "Tamatar smiles"
    framing: closeup
    duration: 3.0
  - id: s3
    action: "Tamatar jumps"
    duration: 3.0
  - id: s4
    action: "Tamatar bows"
    duration: 3.0
`;

function routes() {
  const stages = ["Story", "Cast", "Voices", "Key frames", "Shots", "Assembly"].map((l, i) =>
    stage(l.toLowerCase(), l, i === 0 ? "needs_review" : "not_started", null, i > 1),
  );
  const version = {
    id: "v1id",
    version: 1,
    is_current: true,
    approved_at: null,
    created_at: "2026-11-01T10:00:00Z",
  };
  return [
    (url: URL) => (url.pathname === API ? json(project({ stage: "DRAFT", stages_approved: 0 })) : undefined),
    (url: URL) => (url.pathname === `${API}/stages` ? json({ stages }) : undefined),
    (url: URL) => (url.pathname === `${API}/story` ? json({ ...version, yaml_text: YAML_TEXT }) : undefined),
    (url: URL) => (url.pathname === `${API}/story/versions` ? json([version]) : undefined),
    (url: URL) =>
      url.pathname === "/api/v1/story/schema" ? json({ type: "object", additionalProperties: false }) : undefined,
  ];
}

async function openEditor() {
  stubFetch(routes());
  renderApp(`/projects/${ID}`);
  await screen.findByRole("tab", { name: "YAML" });
  return userEvent.setup();
}

const yamlBox = () => screen.getByRole("textbox", { name: "YAML editor" }) as HTMLTextAreaElement;

describe("Story editor Form and YAML sync", () => {
  it("editing a Form field updates the YAML view", async () => {
    const user = await openEditor();
    const card = await screen.findByLabelText("Scene s1");
    const action = within(card).getByRole("textbox", { name: "Action" });
    await user.clear(action);
    await user.type(action, "Aloo dances");
    await user.click(screen.getByRole("tab", { name: "YAML" }));
    await waitFor(() => expect(yamlBox().value).toContain("action: Aloo dances"));
    expect(yamlBox().value).not.toContain("Tamatar waves");
  });

  it("editing the YAML updates the Form field", async () => {
    const user = await openEditor();
    await user.click(screen.getByRole("tab", { name: "YAML" }));
    fireEvent.change(yamlBox(), { target: { value: YAML_TEXT.replace("Tamatar waves", "Tamatar sings") } });
    await user.click(screen.getByRole("tab", { name: "Form" }));
    const card = await screen.findByLabelText("Scene s1");
    expect((within(card).getByRole("textbox", { name: "Action" }) as HTMLInputElement).value).toBe("Tamatar sings");
  });

  it("invalid YAML keeps the last valid form state and the YAML text", async () => {
    const user = await openEditor();
    await user.click(screen.getByRole("tab", { name: "YAML" }));
    const broken = YAML_TEXT.replace('title: "Tale"', "title: [oops");
    fireEvent.change(yamlBox(), { target: { value: broken } });
    const errors = await screen.findByRole("list", { name: "YAML errors" });
    expect(within(errors).getAllByRole("listitem").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Form" }));
    expect(await screen.findByText("YAML has errors; fix them to keep editing in Form view")).toBeTruthy();
    await user.click(screen.getByRole("tab", { name: "YAML" }));
    expect(yamlBox().value).toBe(broken);
    expect((screen.getByRole("button", { name: "Approve story" }) as HTMLButtonElement).disabled).toBe(true);
  });
});
