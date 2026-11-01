import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "@/api/client";
import { eventToQueryKeys, useEventStream, type ServerEvent } from "@/api/events";
import { FakeWebSocket } from "./helpers";

describe("query keys", () => {
  it("exposes the documented key helpers", () => {
    expect(queryKeys.projects).toEqual(["projects"]);
    expect(queryKeys.project("p1")).toEqual(["project", "p1"]);
    expect(queryKeys.stages("p1")).toEqual(["project", "p1", "stages"]);
    expect(queryKeys.jobs).toEqual(["jobs"]);
    expect(queryKeys.health).toEqual(["health"]);
  });
});

describe("eventToQueryKeys", () => {
  const ev = (type: ServerEvent["type"], data: Record<string, unknown> = {}): ServerEvent => ({ type, data });

  it("maps job.updated to jobs and the project's stages", () => {
    expect(eventToQueryKeys(ev("job.updated", { project_id: "p1" }))).toEqual([["jobs"], ["project", "p1", "stages"]]);
  });
  it("maps job.updated without a project id to jobs only", () => {
    expect(eventToQueryKeys(ev("job.updated", { project_id: null }))).toEqual([["jobs"]]);
  });
  it("maps artifact.created to stages", () => {
    expect(eventToQueryKeys(ev("artifact.created", { project_id: "p1" }))).toEqual([["project", "p1", "stages"]]);
  });
  it("maps stage.changed to projects, project and stages", () => {
    expect(eventToQueryKeys(ev("stage.changed", { project_id: "p1" }))).toEqual([
      ["projects"],
      ["project", "p1"],
      ["project", "p1", "stages"],
    ]);
  });
  it("maps health.changed to health", () => {
    expect(eventToQueryKeys(ev("health.changed", { service: "ltx", status: "fail" }))).toEqual([["health"]]);
  });
});

describe("useEventStream", () => {
  let client: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );

  beforeEach(() => {
    vi.useFakeTimers();
    FakeWebSocket.reset();
    vi.stubGlobal("WebSocket", FakeWebSocket);
    client = new QueryClient();
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("opens one socket at ws(s)://<host>/ws/events and tracks connection state", () => {
    const { result } = renderHook(() => useEventStream(), { wrapper });
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(FakeWebSocket.last.url).toBe(`ws://${window.location.host}/ws/events`);
    expect(result.current.connected).toBe(false);
    act(() => FakeWebSocket.last.simulateOpen());
    expect(result.current.connected).toBe(true);
  });

  it("invalidates the mapped query keys on each message", () => {
    const spy = vi.spyOn(client, "invalidateQueries");
    renderHook(() => useEventStream({ url: "ws://x/ws/events" }), { wrapper });
    expect(FakeWebSocket.last.url).toBe("ws://x/ws/events");
    act(() => FakeWebSocket.last.simulateOpen());
    act(() => FakeWebSocket.last.simulateMessage({ type: "stage.changed", data: { project_id: "p1" } }));
    const keys = spy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toEqual([["projects"], ["project", "p1"], ["project", "p1", "stages"]]);
  });

  it("reconnects with exponential backoff capped at 8 s", () => {
    const { result } = renderHook(() => useEventStream(), { wrapper });
    act(() => FakeWebSocket.last.simulateOpen());
    act(() => FakeWebSocket.last.simulateClose());
    expect(result.current.connected).toBe(false);
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => void vi.advanceTimersByTime(499));
    expect(FakeWebSocket.instances).toHaveLength(1);
    act(() => void vi.advanceTimersByTime(1));
    expect(FakeWebSocket.instances).toHaveLength(2);
    // second failure waits 1000 ms
    act(() => FakeWebSocket.last.simulateClose());
    act(() => void vi.advanceTimersByTime(999));
    expect(FakeWebSocket.instances).toHaveLength(2);
    act(() => void vi.advanceTimersByTime(1));
    expect(FakeWebSocket.instances).toHaveLength(3);
    for (let i = 0; i < 6; i++) {
      act(() => FakeWebSocket.last.simulateClose());
      act(() => void vi.advanceTimersByTime(8000));
    }
    const n = FakeWebSocket.instances.length;
    act(() => FakeWebSocket.last.simulateClose());
    act(() => void vi.advanceTimersByTime(7999));
    expect(FakeWebSocket.instances).toHaveLength(n);
    act(() => void vi.advanceTimersByTime(1));
    expect(FakeWebSocket.instances).toHaveLength(n + 1);
  });
});
