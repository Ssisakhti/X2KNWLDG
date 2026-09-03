/**
 * What every spec in the browser gate shares (`T-209`).
 *
 * Two rules shape everything here.
 *
 * **Nothing is a constant that the server can state.** The recorded walk was
 * performed against the real library -- 86 entities, 118 relations, one page
 * under the contract maximum -- but the same specs run against the committed
 * fixtures, whose graph is seven entities and nine relations. So the expected
 * numbers are *read from the payload the page was answered with*, and the
 * assertions are about agreement between the two rather than about a number
 * typed into a test. That is the same discipline the Vitest integration files
 * follow, and it is what lets one gate serve both libraries.
 *
 * **The seams are the ones the tasks declared.** `data-map-reading`,
 * `data-map-canvas`, `data-map-nodes`, `data-map-result`, `data-map-card`,
 * `data-map-related-entity`, `data-map-stage-omission`, `data-map-quickread`,
 * `data-map-outline`, `data-map-panel` and `data-map-stage` are named in
 * ADR 0005 as the test seam for these surfaces. Reading them here is what
 * makes the ADR's promise ("keep them true if these surfaces are restyled")
 * something a run can check.
 */

import { expect, type Locator, type Page } from "@playwright/test";

/** The graph payload, as much of it as any spec here reads. */
export interface GraphPayload {
  nodes: {
    global_id: string;
    label: string | null;
    kind: string | null;
    provenance_class: string;
    source_id: string | null;
  }[];
  edges: {
    id: string;
    from_id: string;
    to_id: string;
    relation: string;
    relation_vocabulary: string;
    provenance_class: string;
  }[];
  truncated: boolean;
  total: number | null;
}

/**
 * The whole graph the served library holds, from the same operation the Map
 * calls.
 *
 * Requested at the contract maximum (D-118), and `truncated` is asserted
 * false: every "the Map drew what the server sent" assertion below compares
 * against this, and comparing against a cut graph would be a test about the
 * cut.
 */
export async function servedGraph(page: Page): Promise<GraphPayload> {
  const response = await page.request.get("/api/graph?limit=500");
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    data: Omit<GraphPayload, "total">;
    page: { total: number | null };
  };
  expect(body.data.truncated).toBe(false);
  return { ...body.data, total: body.page.total };
}

/** Degree by `global_id`, counting each end of every edge, self-loops twice. */
export function degrees(graph: GraphPayload): Map<string, number> {
  const degree = new Map<string, number>();
  for (const edge of graph.edges) {
    for (const endpoint of [edge.from_id, edge.to_id]) {
      degree.set(endpoint, (degree.get(endpoint) ?? 0) + 1);
    }
  }
  return degree;
}

/**
 * The most connected entity in the served graph, with the identity as a
 * tie-break so a rerun walks the same one.
 *
 * On the real library this is a derived `mental_model` with eight neighbours
 * and thirteen edges among them; on the fixtures it is one of four entities
 * with three. Either way it is the hardest case the served library has, which
 * is the one worth walking.
 */
export function busiest(graph: GraphPayload): string {
  const ranked = [...degrees(graph).entries()].sort(
    (left, right) => right[1] - left[1] || (left[0] < right[0] ? -1 : 1),
  );
  const top = ranked[0];
  expect(top, "the served graph has no edge, so there is no neighbourhood to walk").toBeDefined();
  return (top as [string, number])[0];
}

/** An entity that records a source, so the Reader has somewhere to open. */
export function sourceBacked(graph: GraphPayload): string {
  const found = graph.nodes.find((node) => node.source_id !== null);
  expect(found, "the served graph holds no entity with a source").toBeDefined();
  return (found as GraphPayload["nodes"][number]).global_id;
}

/** The Map route, with the URL grammar's own parameter names (D-119). */
export function mapUrl(params: Record<string, string> = {}): string {
  const query = Object.entries(params)
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");
  return `/#/map${query === "" ? "" : `?${query}`}`;
}

/** The route's own two states, as it renders them. */
export async function reading(page: Page): Promise<{ graph: string; canvas: string }> {
  const root = page.locator(".map");
  return {
    graph: (await root.getAttribute("data-map-reading")) ?? "",
    canvas: (await root.getAttribute("data-map-canvas")) ?? "",
  };
}

/** The counts beside the canvas, read from the attributes rather than the prose. */
export async function counts(page: Page): Promise<{
  nodes: number;
  edges: number;
  held: number;
  complete: boolean;
  truncated: boolean;
}> {
  const panel = page.locator("[data-map-nodes]");
  await expect(panel).toBeVisible();
  const read = async (name: string) => (await panel.getAttribute(name)) ?? "";
  return {
    nodes: Number(await read("data-map-nodes")),
    edges: Number(await read("data-map-edges")),
    held: Number(await read("data-map-held")),
    complete: (await read("data-map-complete")) === "true",
    truncated: (await read("data-map-truncated")) === "true",
  };
}

/**
 * Open the Map and wait until there is a picture.
 *
 * The wait is for the canvas state rather than for the counts, and that is
 * ADR 0005's finding 4 in `T-208`: the counts and the camera do not arrive
 * together, so a test that waited for the counts and then drove the camera
 * was pressing a disabled button and passing anyway.
 */
export async function openDrawnMap(page: Page, params: Record<string, string> = {}): Promise<void> {
  await page.goto(mapUrl(params));
  await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
  await expect(page.locator("[data-map-stage] canvas")).toHaveCount(1);
}

/**
 * Wait until the card overlay has settled over a selection.
 *
 * Two things happen after a focus is chosen, in this order: the camera is
 * framed (D-146) and the cards are placed when it stops moving, which is
 * `MAP_STAGE_SETTLE_MS` after the last frame (D-138). A spec that read the
 * placement between those two would be reading a picture mid-gesture -- and
 * "cards placed plus omissions counted equals the neighbours returned" is a
 * statement about *one* placement, so both numbers must come from the same
 * settled one.
 *
 * The wait is on the primary card, which is the first thing placed, and then
 * a fixed pause long enough for the camera's own easing plus the settle
 * delay. A poll on the property being asserted would pass the moment it
 * happened to hold, which is a test that cannot fail.
 */
export async function settledStage(page: Page): Promise<void> {
  await expect(
    page.locator('.map__overlay [data-map-card][data-map-card-primary="true"]'),
  ).toBeVisible();
  await page.waitForTimeout(700);
}

/**
 * Hunt for a mark under the pointer, by hovering a coarse grid of the stage.
 *
 * The canvas is the one surface with no DOM to query: a node's pixel position
 * is the renderer's own answer and nothing publishes it. So this walks the
 * stage the way a reader does -- moving the pointer until the route says what
 * is under it, which it does through the one transient Peek -- and returns the
 * first mark it finds that is not `exclude`.
 *
 * `null` when the grid found nothing, which is a real answer for a sparse
 * graph and is why the caller decides whether that is a failure.
 *
 * **The grid's resolution is a function of how big a mark is, and `T-216`
 * changed that.** Until D-197 a mark's size was multiplied by the framing, so
 * over the committed seven-node fixtures -- a tiny extent framed into a whole
 * field -- the marks were enormous and a coarse sweep of the middle of the
 * stage could not miss them. They are screen pixels now: a source circle is
 * 12 px across on a 1280 px field, which is the size the approved composition
 * draws and a fifth of the area a 24 px probe grid needs to be sure of a hit.
 * So the step is finer and the budget covers the whole stage rather than its
 * middle, and the two specs that hunt for a mark over the fixtures pass again.
 * The cost is paid only when nothing is found early: the sweep still returns on
 * its first hit, and over the real 86-node library that is within a few dozen
 * probes.
 */
export async function findMark(
  page: Page,
  options: { exclude?: string; step?: number; budget?: number } = {},
): Promise<{ globalId: string; x: number; y: number; clientX: number; clientY: number } | null> {
  const stage = page.locator("[data-map-stage]");
  // Scrolled to first, and this is not a formality: the counts, the filters
  // and the search rail come before the canvas (D-129), so at a 1280x720
  // viewport the stage begins below the fold -- `T-209` measured it at 790 px
  // down the document. A pointer aimed at a box outside the viewport hovers
  // nothing at all, which is also true of a reader.
  await stage.scrollIntoViewIfNeeded();
  const box = await stage.boundingBox();
  if (box === null) return null;
  const step = options.step ?? 14;

  // Nearest the middle first, because a framed focus is in the middle and its
  // neighbours are around it (D-146) -- so the search finds a mark in a few
  // dozen moves rather than sweeping an empty corner of the stage.
  const points: { x: number; y: number }[] = [];
  for (let y = step / 2; y < box.height; y += step) {
    for (let x = step / 2; x < box.width; x += step) points.push({ x, y });
  }
  const centre = { x: box.width / 2, y: box.height / 2 };
  const distance = (point: { x: number; y: number }) =>
    (point.x - centre.x) ** 2 + (point.y - centre.y) ** 2;
  points.sort((left, right) => distance(left) - distance(right));

  /**
   * Whatever the route currently says is under the pointer.
   *
   * Read with `evaluate` rather than through a locator: a locator's
   * `getAttribute` *waits* for the element, and the whole point of each probe
   * here is that the element is usually absent.
   */
  const under = () =>
    page.evaluate(
      () => document.querySelector("[data-map-peek]")?.getAttribute("data-map-peek") ?? null,
    );

  /**
   * Whether this exact point really hovers a mark, and where that point is
   * *now*.
   *
   * The sweep cannot answer the first question on its own, and `T-209`
   * learned it the hard way: a Peek is React state, so it appears a render
   * *after* the move that opened it, and it stays open until the pointer
   * leaves the mark. A sweep that reads immediately after each move therefore
   * reports the hit one probe late -- the coordinate it returns is up to a
   * step away from the mark, the hover assertion passes because the Peek is
   * still open, and the *click* lands on empty canvas.
   *
   * The second question is the other half of the same lesson. The Peek is
   * rendered below the stage (`T-208`), so opening or closing one changes the
   * document's height -- and a document scrolled near its end then has its
   * scroll position clamped, which moves the stage under a coordinate
   * measured before any of that. So the box is measured again with the Peek
   * open, and the caller clicks the coordinates this returns rather than ones
   * it worked out earlier.
   */
  const confirm = async (point: {
    x: number;
    y: number;
  }): Promise<{ globalId: string; clientX: number; clientY: number } | null> => {
    // Escape closes the Peek from anywhere on the route (`T-208`), which is
    // what makes the next move a real transition rather than a no-op.
    await page.keyboard.press("Escape");
    const before = await stage.boundingBox();
    if (before === null) return null;
    await page.mouse.move(before.x + point.x, before.y + point.y - 2);
    await page.waitForTimeout(80);
    await page.mouse.move(before.x + point.x, before.y + point.y);
    await page.waitForTimeout(160);
    const found = await under();
    if (found === null || found === "" || found === options.exclude) return null;
    const after = await stage.boundingBox();
    if (after === null) return null;
    return { globalId: found, clientX: after.x + point.x, clientY: after.y + point.y };
  };

  let previous: { x: number; y: number } | null = null;
  for (const point of points.slice(0, options.budget ?? 6000)) {
    await page.mouse.move(box.x + point.x, box.y + point.y);
    const seen = await under();
    if (seen !== null && seen !== "" && seen !== options.exclude) {
      // This point, or the one before it: the Peek may be a probe behind.
      for (const candidate of previous === null ? [point] : [point, previous]) {
        const confirmed = await confirm(candidate);
        if (confirmed !== null) return { ...confirmed, x: candidate.x, y: candidate.y };
      }
    }
    previous = point;
  }
  return null;
}

/** Every panel on the route, and whether it is open. `Disclosure`'s own seam. */
export async function panels(page: Page): Promise<Record<string, boolean>> {
  return Object.fromEntries(
    await page.locator("[data-map-panel]").evaluateAll((elements) =>
      elements.map((element) => [
        (element as HTMLElement).dataset.mapPanel ?? "",
        (element as HTMLElement).dataset.mapPanelOpen === "true",
      ]),
    ),
  );
}

/** Open a panel by name if it is folded, so a spec can read what is inside it. */
export async function openPanel(page: Page, name: string): Promise<Locator> {
  const panel = page.locator(`[data-map-panel="${name}"]`);
  await expect(panel).toBeVisible();
  if ((await panel.getAttribute("data-map-panel-open")) !== "true") {
    await panel.locator("summary").click();
  }
  await expect(panel).toHaveAttribute("data-map-panel-open", "true");
  return panel;
}

/**
 * Count the WebGL contexts this page has ever created, and how many are still
 * alive.
 *
 * The instrument the `T-202` gate built, installed before the bundle runs.
 * Browsers expose no count of live contexts and answer an excess by losing
 * the *oldest*, so a leak shows up as a blank canvas somewhere unrelated,
 * long after the mistake: ADR 0005 invariant 10 is only checkable by counting.
 *
 * Contexts are held in a `Set`, because `getContext` returns the context a
 * canvas already has -- so a caller that asks a second time (releasing one,
 * for instance) must not be counted as having created a second.
 */
export async function countContexts(page: Page): Promise<void> {
  await page.addInitScript(() => {
    interface Probe {
      __glContexts?: Set<WebGLRenderingContext>;
      __glLostEvents?: number;
    }
    const scope = window as unknown as Probe;
    const contexts = new Set<WebGLRenderingContext>();
    scope.__glContexts = contexts;
    scope.__glLostEvents = 0;
    const original = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function patched(
      this: HTMLCanvasElement,
      ...args: Parameters<HTMLCanvasElement["getContext"]>
    ): ReturnType<HTMLCanvasElement["getContext"]> {
      const context = original.apply(this, args);
      const kind = String(args[0]);
      if (context !== null && (kind === "webgl" || kind === "webgl2")) {
        if (!contexts.has(context as WebGLRenderingContext)) {
          contexts.add(context as WebGLRenderingContext);
          this.addEventListener("webglcontextlost", () => {
            scope.__glLostEvents = (scope.__glLostEvents ?? 0) + 1;
          });
        }
      }
      return context;
    } as HTMLCanvasElement["getContext"];
  });
}

export interface ContextReport {
  created: number;
  lost: number;
  live: number;
  lostEvents: number;
}

/** What the probe has seen so far. `countContexts` must have run first. */
export async function contextReport(page: Page): Promise<ContextReport> {
  return page.evaluate(() => {
    const scope = window as unknown as {
      __glContexts?: Set<WebGLRenderingContext>;
      __glLostEvents?: number;
    };
    const contexts = [...(scope.__glContexts ?? [])];
    const lost = contexts.filter((context) => context.isContextLost()).length;
    return {
      created: contexts.length,
      lost,
      live: contexts.length - lost,
      lostEvents: scope.__glLostEvents ?? 0,
    };
  });
}

/**
 * Collect everything the browser reports that the page did not ask for.
 *
 * Page errors and failed requests are defects. Console warnings are not
 * automatically defects: the `T-202` gate recorded that this Sigma beta logs
 * `GL_INVALID_OPERATION` a few times per context while drawing correctly
 * (ADR 0005, finding 2), so the beta's own noise is named and skipped and
 * anything else is returned for a spec to assert on.
 *
 * D-183: what that costs is stated rather than left implied. The allowlist
 * cannot tell the beta's noise from a *real* `GL_INVALID_OPERATION`, so this
 * gate is blind to that one class of GL error for as long as the renderer is a
 * prerelease. `sigma` is pinned exactly at `4.0.0-beta.5` — right for a
 * prerelease, and it means no upstream fix arrives without a manual bump, and
 * `npm view sigma dist-tags` still has no stable 4.x (`latest` is 3.x, which
 * this Map is not written against). The bump condition: when a stable 4.x
 * ships, take it, delete this allowlist, and run the gate — if it stays green
 * the blindness is gone; if it does not, the errors it now reports were always
 * there.
 */
export function watchForTrouble(page: Page): { trouble: string[] } {
  const trouble: string[] = [];
  const KNOWN_BETA_NOISE = /GL_INVALID_OPERATION|glDrawArraysInstanced/;
  page.on("pageerror", (error) => trouble.push(`pageerror: ${error.message}`));
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (KNOWN_BETA_NOISE.test(text)) return;
    // The favicon this project does not define. Chrome's console line for it
    // is a generic "Failed to load resource", so the *location* is what says
    // which resource -- matching on the message text would either miss it or
    // swallow every failed request, and one of those is the thing this
    // function exists to catch.
    if (message.location().url.includes("favicon")) return;
    trouble.push(`console.error: ${text}`);
  });
  page.on("requestfailed", (request) => {
    if (request.url().includes("favicon")) return;
    trouble.push(`requestfailed: ${request.url()} ${request.failure()?.errorText ?? ""}`);
  });
  page.on("response", (response) => {
    if (response.status() < 400) return;
    if (response.url().includes("favicon")) return;
    trouble.push(`http ${response.status()}: ${response.url()}`);
  });
  return { trouble };
}
