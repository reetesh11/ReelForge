import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { AssemblyScreen } from "@/assembly/AssemblyScreen";
import { json, stubFetch } from "../acceptance/helpers";

const ID = "01ARZ3NDEKTSV4RRFFQ69G5FAV";
const API = `/api/v1/projects/${ID}`;

afterEach(() => vi.unstubAllGlobals());

function state(over: Record<string, unknown> = {}) {
  return {
    stage: "SHOTS_APPROVED", blocked_reason: null, edl: null, edl_hash: null, shots: [], caption_status: {},
    preview: { state: "none", step: null, progress: null, url: null, job_id: null, error: null, rebuild_in_s: null },
    export: { state: "idle", step: null, step_index: null, step_total: null, progress: null, job_id: null, failed_step: null, error: null },
    versions: [], licence_warnings: [], caption_presets: [], ...over,
  };
}

function mount(first: Record<string, unknown>, built?: Record<string, unknown>) {
  const posts: string[] = [];
  stubFetch([
    (url, init) => {
      if (init?.method === "POST") {
        posts.push(url.pathname);
        return json(built ?? first);
      }
      return url.pathname === `${API}/assembly` ? json(first) : undefined;
    },
  ]);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AssemblyScreen projectId={ID} onBack={() => {}} />
    </QueryClientProvider>,
  );
  return posts;
}

it("builds the edit on first open", async () => {
  const posts = mount(state());
  await waitFor(() => expect(posts).toEqual([`${API}/assembly:build`]));
});

it("does not build while shots are not approved, and says why", async () => {
  const posts = mount(state({ blocked_reason: "Approve all shots before exporting." }));
  expect(await screen.findByText("Approve all shots before exporting.")).toBeTruthy();
  expect(posts).toEqual([]);
});

it("shows a missing version and does not open it", async () => {
  const posts = mount(
    state({ versions: [{ version: 1, label: "Reel v1", reel_url: "/media/r", cover_url: "", created_at: "x", missing: true }] }),
  );
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Version" }), "Reel v1");
  expect(await screen.findByText("This version's files are missing.")).toBeTruthy();
  expect(posts.filter((p) => p.endsWith(":open-version"))).toEqual([]);
});

it("opens a version through the API", async () => {
  const posts = mount(
    state({ versions: [{ version: 1, label: "Reel v1", reel_url: "/media/r", cover_url: "", created_at: "x", missing: false }] }),
  );
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Version" }), "Reel v1");
  await waitFor(() => expect(posts).toContain(`${API}/assembly:open-version`));
});
