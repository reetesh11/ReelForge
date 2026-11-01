import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { FakeWebSocket, json, renderApp, stubFetch } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  FakeWebSocket.reset();
});

const check = (name: string, status: string, severity: string, detail: string, fix: string | null) => ({
  name,
  status,
  severity,
  detail,
  fix,
});

function health(drawStatus: string) {
  return {
    status: "fail",
    checks: [
      check("ffmpeg_filters", "pass", "blocking", "ffmpeg 7.1", null),
      check("ltx", "fail", "blocking", "ltx not found", "Install ltx-2-mlx"),
      check("mlx_audio", "pass", "blocking", "mlx-audio 0.2", null),
      check("draw_things", drawStatus, "blocking", "Draw Things reachable", "Start Draw Things"),
      check("ollama", "fail", "warning", "Ollama not running", "Run ollama serve"),
    ],
  };
}

describe("SettingsPage", () => {
  it("shows a coloured row per dependency with detail and fix hints", async () => {
    stubFetch([(url) => (url.pathname === "/health" ? json(health("pass")) : undefined)]);
    renderApp("/settings");
    expect(await screen.findByRole("heading", { name: "Settings & status" })).toBeTruthy();
    const ul = await screen.findByRole("list", { name: "Dependencies" });
    const rows = within(ul).getAllByRole("listitem");
    const byLabel = Object.fromEntries(rows.map((r) => [r.getAttribute("aria-label"), r]));
    expect(Object.keys(byLabel).sort()).toEqual(
      ["Draw Things: green", "Local LLM: amber", "ffmpeg: green", "ltx-2-mlx: red", "mlx-audio: green"].sort(),
    );
    expect(byLabel["ltx-2-mlx: red"]?.textContent).toContain("ltx not found");
    expect(byLabel["ltx-2-mlx: red"]?.textContent).toContain("Fix: Install ltx-2-mlx");
    expect(byLabel["Local LLM: amber"]?.textContent).toContain("Fix: Run ollama serve");
    expect(byLabel["ffmpeg: green"]?.textContent).not.toContain("Fix:");
  });

  it("refreshes when a health.changed event arrives", async () => {
    let drawStatus = "pass";
    stubFetch([(url) => (url.pathname === "/health" ? json(health(drawStatus)) : undefined)]);
    renderApp("/settings");
    await screen.findByLabelText("Draw Things: green");
    drawStatus = "fail";
    FakeWebSocket.last.simulateOpen();
    FakeWebSocket.last.simulateMessage({ type: "health.changed", data: { service: "draw_things", status: "fail" } });
    await waitFor(() => expect(screen.getByLabelText("Draw Things: red")).toBeTruthy());
  });
});
