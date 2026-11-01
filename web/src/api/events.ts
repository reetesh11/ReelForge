import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { queryKeys } from "./client";

export type ServerEvent = {
  type: "job.updated" | "artifact.created" | "stage.changed" | "health.changed";
  data: Record<string, unknown>;
};

type QueryKey = readonly unknown[];

export function eventToQueryKeys(event: ServerEvent): readonly QueryKey[] {
  const projectId = event.data["project_id"];
  const id = typeof projectId === "string" ? projectId : null;
  switch (event.type) {
    case "job.updated":
      return id ? [queryKeys.jobs, queryKeys.stages(id)] : [queryKeys.jobs];
    case "artifact.created":
      return id ? [queryKeys.stages(id)] : [];
    case "stage.changed":
      return id
        ? [queryKeys.projects, queryKeys.project(id), queryKeys.stages(id)]
        : [queryKeys.projects];
    case "health.changed":
      return [queryKeys.health];
  }
}

const BACKOFF_START_MS = 500;
const BACKOFF_CAP_MS = 8000;

function defaultUrl(): string {
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/ws/events`;
}

function parseEvent(raw: unknown): ServerEvent | null {
  if (typeof raw !== "string") return null;
  try {
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return null;
    const { type, data } = parsed as { type?: unknown; data?: unknown };
    if (typeof type !== "string" || typeof data !== "object" || data === null) return null;
    return { type, data } as ServerEvent;
  } catch {
    return null;
  }
}

export function useEventStream(options?: { url?: string }): { connected: boolean } {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);
  const url = options?.url;

  useEffect(() => {
    let disposed = false;
    let failures = 0;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      const ws = new WebSocket(url ?? defaultUrl());
      socket = ws;
      ws.addEventListener("open", () => {
        failures = 0;
        setConnected(true);
      });
      ws.addEventListener("message", (ev) => {
        const event = parseEvent((ev as MessageEvent).data);
        if (!event) return;
        for (const queryKey of eventToQueryKeys(event)) {
          void queryClient.invalidateQueries({ queryKey });
        }
      });
      ws.addEventListener("close", () => {
        if (disposed) return;
        setConnected(false);
        const delay = Math.min(BACKOFF_START_MS * 2 ** failures, BACKOFF_CAP_MS);
        failures += 1;
        timer = setTimeout(connect, delay);
      });
    };

    connect();
    return () => {
      disposed = true;
      if (timer) clearTimeout(timer);
      socket?.close();
    };
  }, [queryClient, url]);

  return { connected };
}
