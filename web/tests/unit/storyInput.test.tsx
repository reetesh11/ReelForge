import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { FakeWebSocket, json, project, renderApp, stage, stubFetch } from "../acceptance/helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

const job = (over: Record<string, unknown>) => ({
  id: "j1",
  project_id: ID,
  type: "story.structure",
  status: "queued",
  priority: 0,
  heavy: false,
  mem_need_gb: 0,
  attempts: 0,
  progress: 0,
  message: null,
  error: null,
  pid: null,
  exit_code: null,
  peak_rss_mb: null,
  command: null,
  payload: {},
  created_at: "2026-11-01T10:00:00Z",
  started_at: null,
  finished_at: null,
  ...over,
});

function setup(jobs: Array<Record<string, unknown>>) {
  let polled = 0;
  const fn = stubFetch([
    (url) => (url.pathname === `${API}/story` ? json({ detail: "no story yet" }, 404) : undefined),
    (url) => (url.pathname === API ? json(project({ stage: "DRAFT", stages_approved: 0 })) : undefined),
    (url) =>
      url.pathname === `${API}/stages`
        ? json({ stages: [stage("story", "Story", "not_started", null, false)] })
        : undefined,
    (url) => (url.pathname === `${API}/story:structure` ? json(job({}), 202) : undefined),
    (url) => (url.pathname === "/api/v1/jobs/j1" ? json(jobs[Math.min(polled++, jobs.length - 1)]) : undefined),
  ]);
  const posted = async (): Promise<unknown[]> => {
    const bodies: unknown[] = [];
    for (const call of fn.mock.calls) {
      const req = call[0];
      if (req instanceof Request && req.url.endsWith("story:structure")) bodies.push(JSON.parse(await req.clone().text()));
    }
    return bodies;
  };
  return { posted };
}

it("shows the input screen with closed sections and a disabled button", async () => {
  setup([]);
  renderApp(`/projects/${ID}`);
  const box = await screen.findByRole("textbox", { name: "Storyline" });
  const button = screen.getByRole("button", { name: "Structure my story" }) as HTMLButtonElement;
  expect(button.disabled).toBe(true);
  for (const name of ["Characters", "Backgrounds/locations", "Product placement", "Dialogue", "Style", "Language", "Target length", "Use characters from library"]) {
    const summary = screen.getByText(name, { selector: "summary" });
    expect((summary.closest("details") as HTMLDetailsElement).open).toBe(false);
  }
  expect(screen.getByText("No saved characters yet. They appear here after Cast (coming later).")).toBeTruthy();
  const user = userEvent.setup();
  await user.type(box, "   ");
  expect(button.disabled).toBe(true);
  await user.type(box, "A tomato");
  expect(button.disabled).toBe(false);
});

it("asks gap questions and re-runs structuring with the answers", async () => {
  const question = { path: "scenes[1].setting", question: "Where does scene 2 happen?" };
  const { posted } = setup([
    job({ status: "succeeded", result: { version: null, questions: [question], draft_yaml: null } }),
    job({ status: "running", progress: 10, message: "Asking the model" }),
  ]);
  renderApp(`/projects/${ID}`);
  const user = userEvent.setup();
  await user.type(await screen.findByRole("textbox", { name: "Storyline" }), "A tomato tale");
  await user.click(screen.getByRole("button", { name: "Structure my story" }));
  const item = (await screen.findByText("Where does scene 2 happen?")).closest("li") as HTMLElement;
  await user.type(within(item).getByRole("textbox", { name: "Where does scene 2 happen?" }), "a kitchen");
  await user.click(within(item).getByRole("button", { name: "Answer" }));
  await waitFor(async () => expect((await posted()).length).toBe(2));
  expect((await posted())[1]).toMatchObject({ answers: [{ path: question.path, answer: "a kitchen" }] });
});

it("shows the job error and Try again", async () => {
  setup([job({ status: "failed", error: "Ollama isn't reachable on port 11434." })]);
  renderApp(`/projects/${ID}`);
  const user = userEvent.setup();
  await user.type(await screen.findByRole("textbox", { name: "Storyline" }), "A tomato tale");
  await user.click(screen.getByRole("button", { name: "Structure my story" }));
  expect(await screen.findByText("Ollama isn't reachable on port 11434.")).toBeTruthy();
  expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
});
