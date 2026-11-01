import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { defineConfig } from "@playwright/test";

const dataRoot = fs.mkdtempSync(path.join(os.tmpdir(), "reelforge-e2e-"));
const repoRoot = path.resolve(__dirname, "..");

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  workers: 1,
  fullyParallel: false,
  use: { baseURL: "http://127.0.0.1:7401" },
  webServer: [
    {
      command: `uv run reelforge up --allow-degraded --backend mock --data-root ${dataRoot} --api-port 7400`,
      cwd: repoRoot,
      url: "http://127.0.0.1:7400/health",
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: "pnpm --dir web dev",
      cwd: repoRoot,
      url: "http://127.0.0.1:7401",
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
