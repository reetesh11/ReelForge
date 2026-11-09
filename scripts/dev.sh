#!/usr/bin/env bash
# One command to run ReelForge: API + worker (port 7400) and the web UI (port 7401).
#   ./scripts/dev.sh            start both; Ctrl+C stops both
#   ./scripts/dev.sh --strict   fail instead of starting degraded when a doctor check fails
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${REELFORGE_CONFIG:-$HOME/ReelForge/config.toml}"
DEGRADED="--allow-degraded"
[[ "${1:-}" == "--strict" ]] && DEGRADED=""

cd "$ROOT"
[[ -d web/node_modules ]] || pnpm --dir web install

UP_ARGS=(up)
[[ -n "$DEGRADED" ]] && UP_ARGS+=("$DEGRADED")
[[ -f "$CONFIG" ]] && UP_ARGS+=(--config "$CONFIG")

pids=()
cleanup() {
  trap - INT TERM EXIT
  for pid in "${pids[@]:-}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap cleanup INT TERM EXIT

uv run reelforge "${UP_ARGS[@]}" &
pids+=($!)
# Start the UI only after the API is up: doctor checks that port 7401 is free.
until curl -sf http://127.0.0.1:7400/health >/dev/null 2>&1; do
  kill -0 "${pids[0]}" 2>/dev/null || { echo "API failed to start" >&2; exit 1; }
  sleep 1
done
pnpm --dir web dev &
pids+=($!)

echo
echo "UI:  http://127.0.0.1:7401   (open this one)"
echo "API: http://127.0.0.1:7400"
echo

# exit as soon as either process dies (portable: macOS bash 3.2 has no `wait -n`)
while kill -0 "${pids[0]}" 2>/dev/null && kill -0 "${pids[1]}" 2>/dev/null; do
  sleep 1
done
