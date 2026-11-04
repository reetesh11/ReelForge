import { useEffect, useState } from "react";

/** Whole seconds since `startedAt` (an ISO time), ticking every second while `running`. */
export function useElapsed(startedAt: string | null | undefined, running: boolean, baseSeconds = 0): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [running]);
  if (!running) return baseSeconds;
  const start = startedAt ? Date.parse(startedAt) : Number.NaN;
  if (Number.isNaN(start)) return baseSeconds;
  return Math.max(0, Math.floor((now - start) / 1000));
}
