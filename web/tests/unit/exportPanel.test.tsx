import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { AssemblyState } from "@/api/assembly";
import { ExportPanel } from "@/assembly/ExportPanel";
import { stubFetch } from "../acceptance/helpers";

afterEach(() => vi.unstubAllGlobals());

function state(over: Partial<AssemblyState> = {}): AssemblyState {
  return {
    stage: "SHOTS_APPROVED", blocked_reason: null, edl: null, edl_hash: null, shots: [], caption_status: {},
    preview: { state: "up_to_date", step: null, progress: null, url: null, job_id: null, error: null, rebuild_in_s: null },
    export: { state: "idle", step: null, step_index: null, step_total: null, progress: null, job_id: null, failed_step: null, error: null },
    versions: [], licence_warnings: [], caption_presets: [], ...over,
  };
}

function mount(s: AssemblyState) {
  stubFetch([]);
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ExportPanel projectId="p" state={s} />
    </QueryClientProvider>,
  );
}

it("is enabled when idle and shows the latest version as exported", () => {
  mount(state({ versions: [{ version: 3, label: "Reel v3", reel_url: "", cover_url: "", created_at: "", missing: false }] }));
  expect((screen.getByRole("button", { name: "Export final" }) as HTMLButtonElement).disabled).toBe(false);
  expect(screen.getByText("Exported reel v3")).toBeTruthy();
});

it("shows progress while running and disables the button", () => {
  mount(
    state({
      export: { state: "running", step: "Encoding", step_index: 8, step_total: 10, progress: 70, job_id: "j", failed_step: null, error: null },
    }),
  );
  expect(screen.getByText("Exporting: Encoding (8 of 10)")).toBeTruthy();
  expect((screen.getByRole("button", { name: "Export final" }) as HTMLButtonElement).disabled).toBe(true);
});

it("shows no dialog until Export is clicked", () => {
  mount(state({ licence_warnings: [{ model: "m", version: "1", licence: "" }] }));
  expect(screen.queryByRole("dialog")).toBeNull();
});
