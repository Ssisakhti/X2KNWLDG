/**
 * The real-browser gate (`T-209`).
 *
 * Phase 2 built the Map behind two witnesses that cannot answer the questions
 * a browser answers: jsdom, which has no WebGL and no layout, and a running
 * server, which knows nothing about what was drawn. `T-202` walked the
 * *renderer* in Chrome by hand through `gate.html`; this walks the **route**,
 * automatically, and it is the last task in the `T-201` epic.
 *
 * What it is pointed at, and why each half is real:
 *
 * - **The built bundle**, served by `vite preview` after `npm run build`, not
 *   the dev server's module graph. `x2knwldg ui` serves `dist/`, and the two
 *   differ in ways that matter here: the renderer is a lazily imported chunk
 *   (D-127), so "the module never loaded" is a real network request in
 *   production and a module-graph edge in development.
 * - **The real API**, `create_app(project_root=...)` through
 *   `scripts/dev_api.py`, forwarded by `vite preview`'s proxy. A mock agrees
 *   with whatever the frontend assumed (D-116), and every number these specs
 *   assert on is read back out of the payload the server actually sent.
 *
 * Two environment variables move it, and neither is needed for a local run:
 *
 * - `X2KNWLDG_BROWSER_PROJECT_ROOT` names a project to serve. Unset serves
 *   the committed `PASS`/`PARTIAL`/`FAIL` run fixtures, so the gate is
 *   hermetic and CI can run it; the recorded walk in ADR 0005 was performed
 *   with this set to the repository root, which is where the real 86-node,
 *   118-edge library lives. Nothing under `output/` is written either way.
 * - `X2KNWLDG_BROWSER_CHANNEL` names the browser. The default is `chrome` --
 *   installed Google Chrome, which on the target machine reaches WebGL2
 *   through `ANGLE Metal` on the GPU, the same path `T-202` recorded. Setting
 *   it empty uses Playwright's bundled Chromium, which answers WebGL2 through
 *   SwiftShader: a software rasteriser, and a useful second witness precisely
 *   because it proves the route needs no GPU.
 *
 * There is no visual golden here, deliberately: `PROJECT_MANAGEMENT.md`
 * `T-209` asks for behaviour and accessible state rather than a cross-platform
 * pixel comparison, and a screenshot of a WebGL canvas differs between a Metal
 * driver and a software rasteriser for reasons that are not defects.
 */

import { defineConfig, devices } from "@playwright/test";

declare const process: { env: Record<string, string | undefined> };

/** Where `dev_api.py` listens for this run. Not 8931, so a hand-started dev API is left alone. */
const API_PORT = process.env.X2KNWLDG_BROWSER_API_PORT ?? "8933";
/** Where the built bundle is served. Not 4173, for the same reason. */
const PREVIEW_PORT = process.env.X2KNWLDG_BROWSER_PORT ?? "4183";

const API_BASE = `http://127.0.0.1:${API_PORT}`;
const BASE_URL = `http://127.0.0.1:${PREVIEW_PORT}`;

/** The project to serve, or the committed fixtures when unset. */
const PROJECT_ROOT = process.env.X2KNWLDG_BROWSER_PROJECT_ROOT;
/**
 * The interpreter that has the `ui` extra. A virtualenv beside the repository
 * is the project's own convention; `X2KNWLDG_PYTHON` is for anywhere else.
 */
const PYTHON = process.env.X2KNWLDG_PYTHON ?? "../.venv/bin/python";
const CHANNEL = process.env.X2KNWLDG_BROWSER_CHANNEL ?? "chrome";

export default defineConfig({
  testDir: "./browser",
  // The gate is a walk, not a load test: the API is one process over one
  // SQLite index and the specs assert on a camera that eases between states,
  // so they run one at a time and read like the walk they are.
  workers: 1,
  fullyParallel: false,
  // A retry hides exactly the flake this gate exists to find.
  retries: 0,
  timeout: 60_000,
  expect: { timeout: 15_000 },
  reporter: process.env.CI === "true" ? [["list"], ["github"]] : [["list"]],
  use: {
    baseURL: BASE_URL,
    ...devices["Desktop Chrome"],
    ...(CHANNEL === "" ? {} : { channel: CHANNEL }),
    // A trace for a failure, and nothing kept for a pass: a green gate that
    // leaves 200 MB of traces behind stops being run.
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  webServer: [
    {
      command: `${PYTHON} scripts/dev_api.py --port ${API_PORT}${
        PROJECT_ROOT === undefined ? "" : ` --project-root ${PROJECT_ROOT}`
      }`,
      url: `${API_BASE}/api/status`,
      // Building the fixture index is a real indexer run over three runs of
      // canonical output, so the first start is not instant.
      timeout: 180_000,
      reuseExistingServer: true,
      stdout: "pipe",
      stderr: "pipe",
    },
    {
      // Built here rather than assumed: a gate that walked a stale `dist/`
      // would report on the last person's code.
      command: `npm run build && npx vite preview --port ${PREVIEW_PORT} --strictPort`,
      url: BASE_URL,
      timeout: 180_000,
      reuseExistingServer: true,
      env: { X2KNWLDG_API_BASE: API_BASE },
      stdout: "pipe",
      stderr: "pipe",
    },
  ],
});

export { API_BASE, BASE_URL };
