/// <reference types="vitest/config" />
/**
 * Dev server, build, and test runner.
 *
 * The proxy is what lets development run against the **real** API rather than
 * a mock: `npm run dev:api` stands up `create_app(project_root=...)` over the
 * committed run fixtures, and every `/api` request from the page is forwarded
 * to it. A mock would agree with whatever the frontend assumed; the real
 * server disagrees, which is the entire value of it.
 *
 * `process` is declared locally rather than pulled in from `@types/node`: the
 * type-check program is `src` plus the generated contract declarations, with
 * `skipLibCheck: false`, and adding a large ambient type package to it buys
 * nothing here.
 */

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

declare const process: { env: Record<string, string | undefined> };

/** Where `npm run dev:api` listens, overridable for a server started by hand. */
const API = process.env.X2KNWLDG_API_BASE ?? "http://127.0.0.1:8931";

export default defineConfig({
  plugins: [react()],
  server: {
    // Loopback only, in development as in production (ADR 0001 invariant 9).
    host: "127.0.0.1",
    proxy: {
      "/api": { target: API, changeOrigin: false },
    },
  },
  // The same forwarding for `vite preview`, because `T-209` walks the
  // **built** bundle rather than the dev server's module graph: the browser
  // gate's whole point is to exercise what `x2knwldg ui` actually serves, and
  // a bundle that never answers `/api` cannot draw a graph. Loopback only
  // here too, and the same target, so the two servers cannot disagree about
  // which API a walk was performed against.
  preview: {
    host: "127.0.0.1",
    proxy: {
      "/api": { target: API, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.ts", "src/**/*.test.tsx"],
    setupFiles: ["src/test/setup.ts"],
    restoreMocks: true,
    css: true,
  },
});
