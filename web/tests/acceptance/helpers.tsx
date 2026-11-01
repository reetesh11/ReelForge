import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";
import { AppRoutes } from "@/AppRoutes";

export function at<T>(arr: readonly T[], i: number): T {
  const v = arr[i];
  if (v === undefined) throw new Error(`no element at ${i}`);
  return v;
}

export type Route = (url: URL, init?: RequestInit) => Response | Promise<Response> | undefined;

export function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

export function stubFetch(routes: Route[]): ReturnType<typeof vi.fn> {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const req = input instanceof Request ? input : null;
    const url = new URL(req ? req.url : String(input), "http://localhost");
    const method = req ? req.method : (init?.method ?? "GET");
    for (const r of routes) {
      const res = await r(url, { ...init, method });
      if (res) return res;
    }
    return json({ detail: "not stubbed " + url.pathname }, 404);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];
  url: string;
  readyState = 0;
  onopen: ((ev: unknown) => void) | null = null;
  onclose: ((ev: unknown) => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onerror: ((ev: unknown) => void) | null = null;
  private listeners: Record<string, Array<(ev: unknown) => void>> = {};
  constructor(url: string | URL) {
    this.url = String(url);
    FakeWebSocket.instances.push(this);
  }
  addEventListener(type: string, cb: (ev: unknown) => void) {
    (this.listeners[type] ??= []).push(cb);
  }
  removeEventListener(type: string, cb: (ev: unknown) => void) {
    this.listeners[type] = (this.listeners[type] ?? []).filter((x) => x !== cb);
  }
  send() {}
  close() {
    this.emit("close", {});
  }
  private emit(type: string, ev: unknown) {
    if (type === "open") this.readyState = 1;
    if (type === "close") this.readyState = 3;
    const direct = { open: this.onopen, close: this.onclose, message: this.onmessage, error: this.onerror }[type];
    direct?.(ev as never);
    (this.listeners[type] ?? []).forEach((cb) => cb(ev));
  }
  simulateOpen() {
    this.emit("open", {});
  }
  simulateMessage(data: unknown) {
    this.emit("message", { data: JSON.stringify(data) });
  }
  simulateClose() {
    this.emit("close", {});
  }
  static reset() {
    FakeWebSocket.instances = [];
  }
  static get last(): FakeWebSocket {
    return at(FakeWebSocket.instances, FakeWebSocket.instances.length - 1);
  }
}

export function newClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
}

export function renderApp(path: string, client: QueryClient = newClient()) {
  vi.stubGlobal("WebSocket", FakeWebSocket);
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={[path]}>
          <AppRoutes />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
  };
}

export const project = (over: Record<string, unknown> = {}) => ({
  id: "01ARZ3NDEKTSV4RRFFQ69G5FAV",
  slug: "tomato-tale",
  title: "Tomato tale",
  data_dir: "projects/2026-11-01_tomato-tale_01ARZ3NDEKTSV4RRFFQ69G5FAV",
  stage: "STORY_APPROVED",
  stages_approved: 1,
  brand_kit_id: null,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-01T11:00:00Z",
  ...over,
});

export const stage = (key: string, label: string, state: string, progress: number | null, locked: boolean) => ({
  key,
  label,
  state,
  progress,
  locked,
});
