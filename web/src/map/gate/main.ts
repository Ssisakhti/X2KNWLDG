/**
 * The `T-202` gate page: the smallest renderer over the real graph.
 *
 * Development-only and deliberately outside the application. It is not routed
 * (`#/map` belongs to `T-204`), it is not linked from the Shell, and
 * `npm run build` does not include it -- Vite's build input is `index.html`
 * alone, and this page is `gate.html`, served only by `npm run dev`. So a
 * harness written to answer one question cannot become a second Map by
 * accident.
 *
 * What it exists to find out, on the real 86-node/118-edge graph and on this
 * machine rather than in a specification:
 *
 * - does the pinned Sigma v4 beta create, update, resize, select and tear down
 *   without an uncaught error;
 * - is every WebGL context actually released on teardown, or does cycling the
 *   renderer leak them until the browser starts losing the oldest;
 * - and how long the synchronous ForceAtlas2 pass takes, since the worker is
 *   permitted only if that number blocks interaction.
 *
 * The instrumentation is the point. A page that merely *looks* right after one
 * create would answer none of those three.
 */

import Sigma from "sigma";

import { ApiFailure } from "../../api/errors";
import { api } from "../../api/client";
import type { GraphResponse } from "../../api/contract";
import { GateSession, type RendererFactory } from "./session";
import type { GateGraph } from "./gateGraph";

/**
 * The pinned renderer, stated here so the page says which version produced the
 * walk. `tests/test_ui_scaffold.py` asserts this equals the exact pin in
 * `web/package.json`, so the two cannot drift and the screenshot cannot
 * misattribute a result to a version that was not running.
 */
const PINNED_SIGMA = "4.0.0-beta.5";

/** The contract's own maximum for one graph page (D-118). */
const CONTRACT_MAX_NODES = 500;

const elements = {
  log: document.getElementById("log") as HTMLElement,
  stage: document.getElementById("stage") as HTMLElement,
  contexts: document.getElementById("contexts") as HTMLElement,
  nodeId: document.getElementById("node-id") as HTMLInputElement,
  limit: document.getElementById("limit") as HTMLInputElement,
};

function log(message: string): void {
  const line = document.createElement("div");
  line.className = "line";
  line.textContent = `${new Date().toISOString().slice(11, 23)}  ${message}`;
  elements.log.prepend(line);
}

function fail(message: string): void {
  const line = document.createElement("div");
  line.className = "line failure";
  line.textContent = `${new Date().toISOString().slice(11, 23)}  ✗ ${message}`;
  elements.log.prepend(line);
}

/**
 * Every WebGL context this page has ever created, so release can be verified
 * rather than assumed.
 *
 * Browsers expose no count of live contexts; they answer an excess by losing
 * the oldest one, which surfaces as a blank canvas somewhere unrelated. So the
 * factory is wrapped once, before any renderer is constructed, and each
 * context is asked afterwards whether it is lost. Sigma v4's `kill` calls
 * `WEBGL_lose_context.loseContext()`, so a correct teardown is observable:
 * created and lost must converge, and `live` must return to zero.
 */
const contexts: WebGLRenderingContext[] = [];
let contextLossEvents = 0;

function instrumentWebGL(): void {
  const original = HTMLCanvasElement.prototype.getContext;
  HTMLCanvasElement.prototype.getContext = function patched(
    this: HTMLCanvasElement,
    ...args: Parameters<HTMLCanvasElement["getContext"]>
  ): ReturnType<HTMLCanvasElement["getContext"]> {
    const context = original.apply(this, args);
    const kind = String(args[0]);
    if (context !== null && (kind === "webgl" || kind === "webgl2" || kind === "experimental-webgl")) {
      contexts.push(context as WebGLRenderingContext);
      this.addEventListener("webglcontextlost", () => {
        contextLossEvents += 1;
        reportContexts();
      });
      reportContexts();
    }
    return context;
  } as HTMLCanvasElement["getContext"];
}

function reportContexts(): void {
  const lost = contexts.filter((context) => context.isContextLost()).length;
  const live = contexts.length - lost;
  elements.contexts.textContent =
    `WebGL contexts — created ${contexts.length}, lost ${lost}, live ${live}` +
    ` · contextlost events ${contextLossEvents}`;
  elements.contexts.dataset.live = String(live);
}

/** The real renderer, and the only place this gate names Sigma's constructor. */
const createRenderer: RendererFactory = (graph: GateGraph, container: HTMLElement) =>
  new Sigma(graph, container, {
    settings: {
      // The container is sized explicitly by the page, so an invalid one is a
      // defect to see rather than to tolerate.
      allowInvalidContainer: false,
      // 86 labels at once is the honest overview; the canvas plan's rule that
      // not every label is drawn simultaneously is Sigma's own default
      // behaviour here, left untouched so the gate measures the library.
      renderLabels: true,
      enableEdgeEvents: true,
    },
  });

const session = new GateSession({
  container: elements.stage,
  createRenderer,
  log,
  onSelect: (nodeId) => {
    elements.nodeId.value = nodeId;
  },
});

let lastPayload: GraphResponse["data"] | null = null;

async function fetchGraph(): Promise<GraphResponse["data"]> {
  const requested = Number(elements.limit.value);
  const limit = Number.isFinite(requested) && requested > 0 ? Math.min(requested, CONTRACT_MAX_NODES) : CONTRACT_MAX_NODES;
  log(`GET /api/graph?limit=${limit}`);
  const response = await api.call("getGraph", { query: { limit } });
  log(
    `api: ${response.data.nodes.length} nodes, ${response.data.edges.length} edges, ` +
      `truncated=${response.data.truncated}, next_cursor=${String(response.page.next_cursor)}`,
  );
  return response.data;
}

function guard(action: () => void | Promise<void>): () => void {
  return () => {
    try {
      const result = action();
      if (result instanceof Promise) {
        result.catch((cause: unknown) => fail(describe(cause)));
      }
    } catch (cause) {
      fail(describe(cause));
    }
    reportContexts();
  };
}

function describe(cause: unknown): string {
  if (cause instanceof ApiFailure) return `${cause.code}: ${cause.message}`;
  if (cause instanceof Error) return `${cause.name}: ${cause.message}`;
  return String(cause);
}

function wire(id: string, action: () => void | Promise<void>): void {
  const button = document.getElementById(id);
  if (button === null) throw new Error(`gate.html is missing #${id}`);
  button.addEventListener("click", guard(action));
}

instrumentWebGL();
reportContexts();
log(`gate: sigma ${PINNED_SIGMA}, exercising the real API through the dev proxy`);

wire("load", async () => {
  lastPayload = await fetchGraph();
  session.create(lastPayload);
});

wire("update", () => {
  session.update();
});

wire("resize", () => {
  // Two sizes, alternating, because a resize that only ever grows would not
  // exercise the shrink path -- where a stale canvas size shows up as a graph
  // drawn outside its own container.
  const wide = elements.stage.clientWidth > 700;
  session.resize(wide ? 520 : 900, wide ? 380 : 560);
});

wire("select", () => {
  const requested = elements.nodeId.value.trim();
  if (requested !== "") {
    session.select(requested);
    return;
  }
  fail("Type a global_id to select. The gate never picks a node for you.");
});

wire("teardown", () => {
  session.teardown();
});

wire("cycle", async () => {
  // The leak question cannot be answered by one create. Browsers cap live
  // contexts at around sixteen and answer an excess by losing the oldest, so a
  // leak is only visible after enough cycles to cross that cap.
  const payload = lastPayload ?? (await fetchGraph());
  lastPayload = payload;
  const cycles = 20;
  const started = performance.now();
  for (let index = 0; index < cycles; index += 1) {
    session.create(payload);
    session.update();
    session.select(payload.nodes[0]?.global_id ?? "");
    session.teardown();
  }
  const elapsed = performance.now() - started;
  log(
    `cycle: ${cycles} create/update/select/teardown rounds in ${elapsed.toFixed(0)} ms ` +
      `(${session.creates} creates, ${session.kills} kills)`,
  );
  reportContexts();
});

window.addEventListener("error", (event) => fail(`uncaught ${event.message}`));
window.addEventListener("unhandledrejection", (event) =>
  fail(`unhandled rejection ${describe(event.reason)}`),
);
