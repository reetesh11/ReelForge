import path from "node:path";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiTarget = `http://127.0.0.1:${process.env["REELFORGE_API_PORT"] ?? "7400"}`;

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget,
      "/media": apiTarget,
      "/ws": { target: apiTarget, ws: true },
    },
  },
});
