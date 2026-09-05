/**
 * What every Source Map spec shares (`T-257`).
 *
 * `gate.ts` is the Knowledge Map's half of this and its two rules hold here
 * unchanged: **nothing is a constant the server can state**, so every expected
 * number is read back out of the payload the page was answered with, and **the
 * seams are the ones the task declared** — `data-map-of`, `data-source-row`,
 * `data-source-card`, `data-source-brief`, `data-source-ku`,
 * `data-source-relations`, `data-source-relation-row`, `data-source-basis`,
 * `data-source-unit-link`, `data-source-returned` and the counts beside it are
 * `T-256`'s and `T-257`'s published surface, and reading them here is what makes
 * "keep them true if these surfaces are restyled" something a run can check.
 *
 * Two things differ from the Knowledge Map's gate, and both are consequences of
 * what `T-256` built rather than choices made here.
 *
 * **There is no Peek, so a mark is found by clicking rather than by hovering.**
 * The Knowledge Map publishes whatever is under the pointer through one
 * transient `data-map-peek`, and `findMark` sweeps for it. The Source Map has no
 * hover surface at all: a mark's only effect is selection. So `findSourceMark`
 * sweeps by *clicking* and reads the URL, which is the same identity a row
 * writes — and that is the assertion, not a workaround for one.
 *
 * **There is no orbit overlay, so there are no cards to measure on the field.**
 * The Knowledge Map seats neighbour cards around a focus and `composition.ts`
 * measures them. The Source Map's neighbours are rows in the drawer, so its
 * composition is the field, the floats and the drawer — which is what
 * `measureSourceComposition` measures instead. This is a real departure from the
 * approved `T-255` compositions and is recorded as one rather than smoothed
 * over; see `sourceVisual.spec.ts`.
 */

import { expect, type Locator, type Page } from "@playwright/test";

import { coveredShare, type Rect } from "./composition";

/** The source graph payload, as much of it as any spec here reads. */
export interface SourceGraphPayload {
  nodes: {
    global_id: string;
    source_id: string | null;
    source_type: string | null;
    label: string | null;
    provenance_class: string;
    kind: string | null;
  }[];
  relations: {
    id: string;
    from_source_id: string;
    to_source_id: string;
    relation_type: string;
    scope: string;
    provenance_class: string;
    basis_total?: number;
  }[];
  truncated: boolean;
  counts: {
    sources_returned: number;
    relations_returned: number;
    relations_omitted: number;
    sources_total: number | null;
  };
}

/** One source's neighbourhood, from the operation the drawer calls. */
export interface SourceNeighbourhood {
  center_id: string;
  source: SourceGraphPayload["nodes"][number];
  source_knowledge: {
    state: "available" | "stale" | "unavailable";
    brief: {
      source_id: string;
      status: string;
      thesis: { content: string; based_on: string[] };
      key_points: { id: string; content: string; based_on: string[] }[];
      limitations_or_tensions: { id: string; content: string; based_on: string[] }[];
    } | null;
    reason: string | null;
  };
  incoming: SourceRelationDetail[];
  outgoing: SourceRelationDetail[];
  neighbors: SourceGraphPayload["nodes"];
  truncated: boolean;
}

export interface SourceRelationDetail {
  id: string;
  from_source_id: string;
  to_source_id: string;
  relation_type: string;
  scope: string;
  rationale: string;
  basis: { from_ku_id: string; to_ku_id: string; relation_type: string }[];
  basis_total: number;
  basis_returned: number;
}

/**
 * The whole source graph the served library holds.
 *
 * Asked at a limit above the corpus, and `truncated` is asserted false for the
 * same reason `servedGraph` does it: every "the Map drew what the server sent"
 * assertion compares against this, and comparing against a cut graph would be an
 * assertion about the cut. The bounded case is asked for explicitly, by the one
 * spec that is about bounding.
 */
export async function servedSourceGraph(page: Page): Promise<SourceGraphPayload> {
  const response = await page.request.get("/api/source-graph?limit=200");
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as { data: SourceGraphPayload };
  expect(body.data.truncated).toBe(false);
  return body.data;
}

/** One source's neighbourhood, by the two-part id the endpoint takes. */
export async function servedNeighbourhood(
  page: Page,
  sourceId: string,
): Promise<SourceNeighbourhood> {
  const response = await page.request.get(
    `/api/source-graph/neighborhood/${encodeURIComponent(sourceId)}`,
  );
  expect(response.ok(), `the index does not hold ${sourceId}`).toBe(true);
  const body = (await response.json()) as { data: SourceNeighbourhood };
  return body.data;
}

/** The Source Map's URL, in the grammar's own parameter names. */
export function sourceMapUrl(params: Record<string, string> = {}): string {
  const query = Object.entries({ of: "sources", ...params })
    .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
    .join("&");
  return `/#/map?${query}`;
}

/** The three-part node id for a two-part source id, as the graph states it. */
export function nodeIdOf(graph: SourceGraphPayload, sourceId: string): string {
  const node = graph.nodes.find((candidate) => candidate.source_id === sourceId);
  expect(node, `the served graph holds no source ${sourceId}`).toBeDefined();
  return (node as SourceGraphPayload["nodes"][number]).global_id;
}

/**
 * A source that stands in at least one relationship, and one that stands in
 * none.
 *
 * Both are needed and neither is a constant: the phase asks for a relationship
 * with valid basis *and* for "a no-relation fixture emits none", so a spec has
 * to be handed each from whatever the server actually holds. Sorted by id so a
 * rerun walks the same one.
 */
export function relatedSource(graph: SourceGraphPayload): string {
  const withEdges = graph.nodes
    .map((node) => node.source_id)
    .filter((id): id is string => id !== null)
    .filter((id) =>
      graph.relations.some(
        (relation) => relation.from_source_id === id || relation.to_source_id === id,
      ),
    )
    .sort();
  const first = withEdges[0];
  expect(first, "no source in the served graph stands in a relationship").toBeDefined();
  return first as string;
}

export function lonelySource(graph: SourceGraphPayload): string {
  const without = graph.nodes
    .map((node) => node.source_id)
    .filter((id): id is string => id !== null)
    .filter(
      (id) =>
        !graph.relations.some(
          (relation) => relation.from_source_id === id || relation.to_source_id === id,
        ),
    )
    .sort();
  const first = without[0];
  expect(first, "every source in the served graph stands in a relationship").toBeDefined();
  return first as string;
}

/** Open the Source Map and wait until there is a picture. */
export async function openDrawnSourceMap(
  page: Page,
  params: Record<string, string> = {},
): Promise<void> {
  await page.goto(sourceMapUrl(params));
  await expect(page.locator('.map[data-map-of="sources"][data-map-canvas="drawing"]')).toBeVisible();
  await expect(page.locator("[data-map-stage] canvas")).toHaveCount(1);
}

/** The four counts beside the field, read from the attributes not the prose. */
export async function sourceCounts(page: Page): Promise<{
  sources: number;
  relations: number;
  omitted: number;
  total: number | null;
  offPage: number;
  truncated: boolean;
}> {
  const panel = page.locator("[data-source-returned]");
  await expect(panel).toBeVisible();
  const read = async (name: string) => (await panel.getAttribute(name)) ?? "";
  const total = await read("data-source-total");
  return {
    sources: Number(await read("data-source-returned")),
    relations: Number(await read("data-source-relations-returned")),
    omitted: Number(await read("data-source-omitted")),
    total: total === "" ? null : Number(total),
    offPage: Number(await read("data-source-offpage")),
    truncated: (await read("data-source-truncated")) === "true",
  };
}

/**
 * Select a source through its row, and wait for the drawer that answers.
 *
 * The row is the accessible path and therefore the one every spec that is not
 * *about* the canvas uses to get somewhere. It returns once the card for that
 * source is on screen, which is the neighbourhood having arrived rather than the
 * click having been dispatched.
 */
export async function focusByRow(page: Page, sourceId: string): Promise<Locator> {
  const panel = page.locator('[data-map-panel="source-outline"]');
  await expect(panel).toBeVisible();
  if ((await panel.getAttribute("data-map-panel-open")) !== "true") {
    await panel.locator("summary").click();
  }
  await page.locator(`[data-source-row="${cssEscape(sourceId)}"] button`).click();
  const card = page.locator(`[data-source-card="${cssEscape(sourceId)}"]`);
  await expect(card).toBeVisible();
  return card;
}

/** A source id inside an attribute selector; ids carry `:` and digits. */
export function cssEscape(value: string): string {
  return value.replace(/["\\]/gu, "\\$&");
}

/**
 * Hunt for a mark on the stage by clicking a grid of it, and say which source
 * was selected.
 *
 * The Source Map has no hover surface, so unlike `findMark` this cannot probe
 * without committing: each probe is a real click, and a click on empty canvas
 * does nothing at all. That is what makes the sweep sound — the URL changes only
 * when a mark was actually hit — and it is also why the sweep starts at the
 * middle, where a framed graph is.
 *
 * `null` when the grid found nothing, which the caller decides about.
 */
export async function findSourceMark(
  page: Page,
  options: { step?: number; budget?: number } = {},
): Promise<{ sourceId: string; nodeId: string } | null> {
  const stage = page.locator("[data-map-stage]");
  await stage.scrollIntoViewIfNeeded();
  const box = await stage.boundingBox();
  if (box === null) return null;
  const step = options.step ?? 14;

  const points: { x: number; y: number }[] = [];
  for (let y = step / 2; y < box.height; y += step) {
    for (let x = step / 2; x < box.width; x += step) points.push({ x, y });
  }
  const centre = { x: box.width / 2, y: box.height / 2 };
  points.sort(
    (left, right) =>
      (left.x - centre.x) ** 2 +
      (left.y - centre.y) ** 2 -
      ((right.x - centre.x) ** 2 + (right.y - centre.y) ** 2),
  );

  const focused = () =>
    page.evaluate(() => {
      const query = window.location.hash.split("?")[1] ?? "";
      return new URLSearchParams(query).get("focus");
    });

  for (const point of points.slice(0, options.budget ?? 4000)) {
    // Measured again per probe: selecting a source opens the drawer, which
    // changes the layout, so a coordinate worked out before the first hit is
    // not the coordinate it was.
    const now = await stage.boundingBox();
    if (now === null) return null;
    await page.mouse.click(now.x + point.x, now.y + point.y);
    const nodeId = await focused();
    if (nodeId !== null && nodeId !== "") {
      const sourceId = nodeId.split(":").slice(0, -1).join(":");
      return { sourceId, nodeId };
    }
  }
  return null;
}

/** The composition of the Source Map's field, measured on screen, once. */
export interface SourceCompositionReport {
  tier: string | null;
  direction: string;
  field: Rect | null;
  viewport: { width: number; height: number };
  documentHeight: number;
  /** Every floating control, so a spec can name the one that is in the way. */
  chrome: { name: string; rect: Rect }[];
  chromeShare: number;
  /** Floats that overlap each other: the Source Map's own "no two surfaces". */
  collided: string[];
  /** The drawer, and whether it can reach its own foot (`T-256` found it could not). */
  drawer: { scrollHeight: number; clientHeight: number; overflowY: string; bottom: number } | null;
}

export async function measureSourceComposition(page: Page): Promise<SourceCompositionReport> {
  const report = await page.evaluate(() => {
    const route = document.querySelector(".map");
    const stage = document.querySelector("[data-map-stage]");
    const box = stage === null ? null : stage.getBoundingClientRect();
    const rectOf = (rect: DOMRect) => ({
      left: rect.left,
      top: rect.top,
      right: rect.right,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height,
    });
    const field = box === null ? null : rectOf(box);

    const chrome = [...document.querySelectorAll("[data-map-chrome]")].map((node) => ({
      name: node.className,
      rect: rectOf(node.getBoundingClientRect()),
    }));

    const collided: string[] = [];
    for (let i = 0; i < chrome.length; i += 1) {
      for (let j = i + 1; j < chrome.length; j += 1) {
        const one = chrome[i];
        const two = chrome[j];
        if (one === undefined || two === undefined) continue;
        if (one.rect.width === 0 || two.rect.width === 0) continue;
        if (
          one.rect.left < two.rect.right &&
          two.rect.left < one.rect.right &&
          one.rect.top < two.rect.bottom &&
          two.rect.top < one.rect.bottom
        ) {
          collided.push(`${one.name} / ${two.name}`);
        }
      }
    }

    const drawerNode = document.querySelector(".map__drawer");
    const drawer =
      drawerNode === null
        ? null
        : {
            scrollHeight: drawerNode.scrollHeight,
            clientHeight: drawerNode.clientHeight,
            overflowY: getComputedStyle(drawerNode).overflowY,
            bottom: drawerNode.getBoundingClientRect().bottom,
          };

    return {
      tier: route === null ? null : route.getAttribute("data-map-tier"),
      direction: document.documentElement.getAttribute("dir") ?? "ltr",
      field,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      documentHeight: document.documentElement.scrollHeight,
      chrome,
      collided,
      drawer,
    };
  });
  // The same union-of-rectangles arithmetic the Knowledge Map's gate uses, from
  // the same implementation: a second copy is a second number that can disagree
  // with the one the approved captures were measured by.
  return {
    ...report,
    chromeShare: coveredShare(
      report.field,
      report.chrome.map((control) => control.rect),
    ),
  };
}
