import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { SettingsPage } from "@/routes/SettingsPage";

afterEach(() => vi.unstubAllGlobals());

const HEALTH = {
  status: "ok",
  checks: [{ name: "mlx_audio", status: "pass", severity: "blocking", detail: "mlx-audio ready (selftest passed)", fix: null }],
};

function model(key: "omnivoice" | "kokoro") {
  return {
    voice_model: key,
    label: key === "omnivoice" ? "OmniVoice" : "Kokoro (fallback)",
    model_id: key === "omnivoice" ? "mlx-community/OmniVoice-bfloat16" : "mlx-community/Kokoro-82M-bf16",
    choices: [
      { key: "omnivoice", label: "OmniVoice" },
      { key: "kokoro", label: "Kokoro (fallback)" },
    ],
  };
}

const reply = (body: unknown) =>
  new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } });

function setup() {
  let current: "omnivoice" | "kokoro" = "omnivoice";
  const puts: unknown[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const req = input instanceof Request ? input : null;
      const url = new URL(req ? req.url : String(input), "http://localhost");
      const method = req ? req.method : (init?.method ?? "GET");
      if (url.pathname === "/api/v1/voice-model" && method === "PUT") {
        const body = req ? ((await req.json()) as { voice_model: "omnivoice" | "kokoro" }) : { voice_model: current };
        puts.push(body);
        current = body.voice_model;
        return reply(model(current));
      }
      if (url.pathname === "/api/v1/voice-model") return reply(model(current));
      return reply(HEALTH);
    }),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SettingsPage />
    </QueryClientProvider>,
  );
  return puts;
}

it("shows the model line, the mlx-audio detail and no licence warning", async () => {
  setup();
  expect(await screen.findByText("Voice model: OmniVoice (mlx-community/OmniVoice-bfloat16)")).toBeTruthy();
  expect(screen.getByLabelText("mlx-audio: green").textContent).toContain("selftest passed");
  expect(screen.queryByLabelText(/licence/i)).toBeNull();
});

it("changes the voice model with the select", async () => {
  const puts = setup();
  const select = await screen.findByLabelText("Voice model");
  expect(screen.getByRole("option", { name: "Kokoro (fallback)" })).toBeTruthy();
  await userEvent.selectOptions(select, "kokoro");
  await waitFor(() => expect(puts).toEqual([{ voice_model: "kokoro" }]));
  expect(await screen.findByText(/Voice model: Kokoro \(fallback\)/)).toBeTruthy();
});
