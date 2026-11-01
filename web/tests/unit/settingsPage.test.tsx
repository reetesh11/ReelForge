import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { colourOf, SettingsPage } from "@/routes/SettingsPage";

afterEach(() => vi.unstubAllGlobals());

it("maps status and severity to colours", () => {
  const base = { name: "x", detail: "d", fix: null };
  expect(colourOf({ ...base, status: "pass", severity: "blocking" })).toBe("green");
  expect(colourOf({ ...base, status: "fail", severity: "warning" })).toBe("amber");
  expect(colourOf({ ...base, status: "fail", severity: "blocking" })).toBe("red");
});

it("shows a fix hint only for non-green rows", async () => {
  const body = {
    status: "degraded",
    checks: [
      { name: "ollama", status: "fail", severity: "warning", detail: "down", fix: "ollama serve" },
      { name: "ltx", status: "pass", severity: "blocking", detail: "ok", fix: null },
    ],
  };
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json" } })));
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SettingsPage />
    </QueryClientProvider>,
  );
  expect((await screen.findByLabelText("Local LLM: amber")).textContent).toContain("Fix: ollama serve");
  expect(screen.getByLabelText("ltx-2-mlx: green").textContent).not.toContain("Fix:");
});
