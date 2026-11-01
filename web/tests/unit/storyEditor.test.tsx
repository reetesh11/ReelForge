import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { FakeWebSocket, json, project, renderApp, stage, stubFetch } from "../acceptance/helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

const TEXT = `version: 1
title: "Tale"
language: english
target_seconds: 12
characters:
  tomato:
    name: "Tamatar"
    look: "red tomato"
scenes:
  - id: s1
    action: "one"
    duration: 3.0
  - id: s2
    speaker: tomato
    line: "Hello"
    suggested: true
    action: "two"
`;
const OLD = TEXT.replace("Tale", "Old tale");

const v = (n: number, current: boolean, approved: string | null = null) => ({
  id: `v${n}`,
  version: n,
  is_current: current,
  approved_at: approved,
  created_at: "2026-11-01T10:00:00Z",
});

function setup(opts: { approved?: boolean } = {}) {
  const approvedAt = opts.approved ? "2026-11-01T11:00:00Z" : null;
  const fn = stubFetch([
    (url) => (url.pathname === API ? json(project({ stage: "DRAFT", stages_approved: 0 })) : undefined),
    (url) =>
      url.pathname === `${API}/stages` ? json({ stages: [stage("story", "Story", "needs_review", null, false)] }) : undefined,
    (url, init) =>
      url.pathname === `${API}/story` && init?.method === "GET" ? json({ ...v(2, true, approvedAt), yaml_text: TEXT }) : undefined,
    (url) => (url.pathname === `${API}/story/versions` ? json([v(2, true, approvedAt), v(1, false, "2026-10-31T10:00:00Z")]) : undefined),
    (url) => (url.pathname === `${API}/story/versions/1` ? json({ ...v(1, false), yaml_text: OLD }) : undefined),
    (url, init) =>
      url.pathname === `${API}/story` && init?.method === "PUT" ? json({ ...v(3, true), affected: [] }) : undefined,
    (url) => (url.pathname === `${API}/story:approve` ? json(project({ stage: "STORY_APPROVED" })) : undefined),
    (url) => (url.pathname === "/api/v1/story/schema" ? json({}) : undefined),
  ]);
  return fn;
}

const button = (name: string) => screen.getByRole("button", { name }) as HTMLButtonElement;

it("shows header, length and disables Approve until saved", async () => {
  setup();
  renderApp(`/projects/${ID}`);
  expect(await screen.findByRole("heading", { name: "Tale" })).toBeTruthy();
  expect(screen.getByText("Estimated length: 3 s of 12 s target (1 scene has no duration yet)")).toBeTruthy();
  await screen.findByRole("combobox", { name: "Version" });
  expect(button("Approve story").disabled).toBe(false);
  expect(button("Save").disabled).toBe(true);
  const user = userEvent.setup();
  const card = screen.getByLabelText("Scene s1");
  await user.type(within(card).getByRole("textbox", { name: "Action" }), "!");
  expect(button("Approve story").disabled).toBe(true);
  expect(button("Approve story").title).toBe("Save your changes first");
  expect(button("Save").disabled).toBe(false);
});

it("confirms before approving with suggested lines", async () => {
  setup();
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  renderApp(`/projects/${ID}`);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Approve story" }));
  expect(confirm).toHaveBeenCalledWith("1 lines are still marked suggested. Approve anyway?");
  confirm.mockRestore();
});

it("accepting a suggestion removes the flag in the YAML", async () => {
  setup();
  renderApp(`/projects/${ID}`);
  const user = userEvent.setup();
  const card = await screen.findByLabelText("Scene s2");
  expect(within(card).getByText("suggested")).toBeTruthy();
  await user.click(within(card).getByRole("button", { name: "Accept" }));
  await user.click(screen.getByRole("tab", { name: "YAML" }));
  expect((screen.getByRole("textbox", { name: "YAML editor" }) as HTMLTextAreaElement).value).not.toContain("suggested");
});

it("adds a scene with the next id and shows YAML errors for broken text", async () => {
  setup();
  renderApp(`/projects/${ID}`);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "Add scene" }));
  expect(await screen.findByLabelText("Scene s3")).toBeTruthy();
  await user.click(screen.getByRole("tab", { name: "YAML" }));
  fireEvent.change(screen.getByRole("textbox", { name: "YAML editor" }), { target: { value: "title: [oops" } });
  const errors = await screen.findByRole("list", { name: "YAML errors" });
  expect(within(errors).getAllByRole("listitem").length).toBeGreaterThan(0);
});

it("shows an older version read-only and restores it as a new version", async () => {
  const fn = setup();
  renderApp(`/projects/${ID}`);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: "v1" }));
  const text = (await screen.findByRole("textbox", { name: "Version text" })) as HTMLTextAreaElement;
  await waitFor(() => expect(text.value).toContain("Old tale"));
  expect(text.readOnly).toBe(true);
  await user.click(screen.getByRole("button", { name: "Restore as new version" }));
  await waitFor(() => {
    const put = fn.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === "PUT");
    expect(put?.[1]).toMatchObject({ body: OLD });
  });
});

it("shows the approved banner", async () => {
  setup({ approved: true });
  renderApp(`/projects/${ID}`);
  expect(await screen.findByText("Story approved. Editing it will mark dependent items for update.")).toBeTruthy();
});
