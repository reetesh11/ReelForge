import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook } from "@testing-library/react";
import type { ReactNode } from "react";
import { expect, it, vi } from "vitest";
import { eventToQueryKeys, useEventStream } from "@/api/events";

class Sock {
  static all: Sock[] = [];
  listeners: Record<string, Array<(e: unknown) => void>> = {};
  constructor(public url: string) {
    Sock.all.push(this);
  }
  addEventListener(t: string, cb: (e: unknown) => void) {
    (this.listeners[t] ??= []).push(cb);
  }
  close() {}
  fire(t: string, e: unknown = {}) {
    (this.listeners[t] ?? []).forEach((cb) => cb(e));
  }
}

it("ignores events without a project id for stage keys", () => {
  expect(eventToQueryKeys({ type: "artifact.created", data: {} })).toEqual([]);
  expect(eventToQueryKeys({ type: "stage.changed", data: {} })).toEqual([["projects"]]);
});

it("ignores malformed frames and reconnects after close", () => {
  vi.useFakeTimers();
  vi.stubGlobal("WebSocket", Sock);
  Sock.all = [];
  const client = new QueryClient();
  const spy = vi.spyOn(client, "invalidateQueries");
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  renderHook(() => useEventStream({ url: "ws://x" }), { wrapper });
  act(() => Sock.all[0]?.fire("message", { data: "not json" }));
  expect(spy).not.toHaveBeenCalled();
  act(() => Sock.all[0]?.fire("close"));
  act(() => void vi.advanceTimersByTime(500));
  expect(Sock.all).toHaveLength(2);
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
