import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AssemblyScreen } from "@/assembly/AssemblyScreen";
import { json, stubFetch } from "../acceptance/helpers";

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

afterEach(() => vi.unstubAllGlobals());

const shot = (id: string, art: string) => ({
  scene_id: id, artifact: art, source_duration_s: 3, in_s: 0, out_s: 3, transition_in_s: 0,
});

function body() {
  return {
    stage: "SHOTS_APPROVED", blocked_reason: null,
    edl: {
      version: 1, fps: 24, width: 1080, height: 1920, project_id: ID, video: [shot("s1", "a1"), shot("s2", "a2")],
      dialogue: [], captions: [], caption_style: "auto",
    },
    edl_hash: "h",
    shots: [
      { scene_id: "s1", takes: [{ id: "a1", take_no: 1, active: true, video_url: "/media/a1" }] },
      { scene_id: "s2", takes: [{ id: "a2", take_no: 1, active: true, video_url: "/media/a2" }, { id: "a3", take_no: 2, active: false, video_url: "/media/a3" }] },
    ],
    caption_status: {},
    preview: { state: "up_to_date", step: null, progress: null, url: "/media/p", job_id: null, error: null, rebuild_in_s: null },
    export: { state: "idle", step: null, step_index: null, step_total: null, progress: null, job_id: null, failed_step: null, error: null },
    versions: [], licence_warnings: [], caption_presets: [],
  };
}

function mount(editReply: Response | (() => Response)) {
  const sent: Array<Record<string, unknown>> = [];
  stubFetch([
    (url, init) => {
      if (init?.method === "POST" && url.pathname.endsWith(":edit")) {
        sent.push(JSON.parse(String(init.body)) as Record<string, unknown>);
        return typeof editReply === "function" ? editReply() : editReply;
      }
      return url.pathname === `${API}/assembly` ? json(body()) : undefined;
    },
  ]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AssemblyScreen projectId={ID} onBack={() => {}} />
    </QueryClientProvider>,
  );
  return sent;
}

it("shows an edit error in an alert", async () => {
  const sent = mount(json({ detail: "A shot must be at least 0.5 s long." }, 422));
  const input = await screen.findByRole("spinbutton", { name: "Trim out for s1" });
  await userEvent.clear(input);
  await userEvent.type(input, "0.2");
  fireEvent.blur(input);
  expect((await screen.findByRole("alert")).textContent).toBe("A shot must be at least 0.5 s long.");
  expect(sent[0]).toMatchObject({ op: "trim", scene_id: "s1", in_s: 0, out_s: 0.2 });
});

it("shows notes from an edit as plain text", async () => {
  mount(json({ assembly: body(), notes: ["Crossfade shortened to fit"] }));
  const input = await screen.findByRole("spinbutton", { name: "Crossfade into s2" });
  await userEvent.clear(input);
  await userEvent.type(input, "0.5");
  fireEvent.blur(input);
  expect(await screen.findByText("Crossfade shortened to fit")).toBeTruthy();
});

it("swaps the take and cannot move the first shot earlier", async () => {
  const sent = mount(json({ assembly: body(), notes: [] }));
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Take for s2" }), "Take 2");
  await waitFor(() => expect(sent[0]).toMatchObject({ op: "swap_take", scene_id: "s2", take_id: "a3" }));
  expect((screen.getByRole("button", { name: "Move s1 earlier" }) as HTMLButtonElement).disabled).toBe(true);
});
