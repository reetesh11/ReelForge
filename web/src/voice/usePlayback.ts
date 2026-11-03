import { useCallback, useState } from "react";

/** State for the board's shared `<audio autoPlay>` element: play a URL (again), or stop. */
export function usePlayback() {
  const [state, setState] = useState<{ url: string | null; nonce: number }>({ url: null, nonce: 0 });
  const play = useCallback((url: string) => setState((s) => ({ url, nonce: s.nonce + 1 })), []);
  const stop = useCallback(() => setState((s) => ({ url: null, nonce: s.nonce + 1 })), []);
  return { url: state.url, nonce: state.nonce, play, stop };
}
