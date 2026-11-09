import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { SoundScreen } from "@/sound/SoundScreen";

afterEach(() => vi.unstubAllGlobals());

it("shows the approve-all button only while a cue is suggested", async () => {
  const body = {
    engine: { ok: true, message: "" },
    settings: { duck_db: 9, attack_s: 0.15, release_s: 0.4, silence_fade_s: 0.08 },
    cues: [
      {
        id: "a", kind: "sfx", order: 1, state: "suggested", start: { scene: "s1" }, duration: 1,
        source: "generate", start_s: 0, end_s: 1, duration_s: 1, licence: "", picked_take_id: null,
        takes: [], job: null,
      },
    ],
  };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status: 200 })));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <SoundScreen projectId="p" onBack={() => {}} onContinue={() => {}} />
    </QueryClientProvider>,
  );
  expect(await screen.findByRole("button", { name: "Approve all" })).toBeTruthy();
});
