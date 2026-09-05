/**
 * The Source Map's journey, in a real browser (`T-257`).
 *
 * `T-256` built this surface and proved it in jsdom, end to end, **with no
 * renderer at all** — which is a strong witness for the reading path and no
 * witness at all for the picture, the layout, the camera or the URL. This is the
 * walk, and the acceptance question it answers is the phase's own:
 *
 *   does a reader arrive at a source, learn what it says, learn what it stands
 *   in relation to and on what grounds, and get from there into the records?
 *
 * Every expected number below is read out of the payload the page was answered
 * with. Nothing is typed into this file: the served library is a fixture corpus
 * today and could be a real one tomorrow, and a gate that agreed with a constant
 * would be a gate about the constant.
 */

import { expect, test } from "@playwright/test";

import { countContexts, contextReport, mapUrl, openDrawnMap, watchForTrouble } from "./gate";
import {
  cssEscape,
  findSourceMark,
  focusByRow,
  lonelySource,
  nodeIdOf,
  openDrawnSourceMap,
  relatedSource,
  servedNeighbourhood,
  servedSourceGraph,
  sourceCounts,
  sourceMapUrl,
} from "./sourceGate";

test.describe("the Source Map, opened", () => {
  test("draws one mark per acquired source, and says the four counts apart", async ({ page }) => {
    const { trouble } = watchForTrouble(page);
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);

    // The phase's first acceptance clause: *every* implemented source appears,
    // and appears exactly once. Asserted over the list, because the list is the
    // complete view — a bounded field may not have drawn a label, and no mark
    // can be counted from outside the canvas.
    const outline = page.locator("[data-source-outline]");
    await expect(outline).toHaveAttribute("data-source-outline", String(graph.nodes.length));
    const rows = await page.locator("[data-source-row]").evaluateAll((nodes) =>
      nodes.map((node) => (node as HTMLElement).dataset.sourceRow ?? ""),
    );
    expect(rows).toHaveLength(graph.nodes.length);
    expect(new Set(rows).size).toBe(rows.length);
    expect([...rows].sort()).toEqual(
      graph.nodes.map((node) => node.source_id ?? node.global_id).sort(),
    );

    // Four numbers, stated separately because the response states them
    // separately. Adding them into one would be the Map inventing a total.
    expect(await sourceCounts(page)).toEqual({
      sources: graph.counts.sources_returned,
      relations: graph.counts.relations_returned,
      omitted: graph.counts.relations_omitted,
      total: graph.counts.sources_total,
      offPage: 0,
      truncated: false,
    });

    // The picture is labelled as a picture only while there is one.
    const stage = page.locator("[data-map-stage]");
    await expect(stage).toHaveAttribute("role", "img");
    expect(trouble).toEqual([]);
  });

  test("says on its face what it will not tell you", async ({ page }) => {
    await openDrawnSourceMap(page);
    // The two load-bearing refusals, in the chrome rather than only in a
    // comment: no ranking (D-247) and no freshness (D-274). A build that
    // started drawing either would still pass every count assertion above.
    const counts = page.locator('[data-map-panel="source-counts"]');
    if ((await counts.getAttribute("data-map-panel-open")) !== "true") {
      await counts.locator("summary").click();
    }
    await expect(counts.locator(".refusals li")).toHaveCount(2);
    const refusals = (await counts.locator(".refusals").innerText()).toLowerCase();
    expect(refusals).toMatch(/rank|weight|size/);
    expect(refusals).toMatch(/current|fresh|stale/);
  });

  test("is a link: the mode, the selection and a reload all come from the URL", async ({
    page,
  }) => {
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const nodeId = nodeIdOf(graph, chosen);

    // Opened cold, with the selection already in the address.
    await openDrawnSourceMap(page, { focus: nodeId });
    await expect(page.locator(`[data-source-card="${cssEscape(chosen)}"]`)).toBeVisible();

    // Reloaded, to the same picture from the same address.
    await page.reload();
    await expect(page.locator('.map[data-map-of="sources"][data-map-canvas="drawing"]')).toBeVisible();
    await expect(page.locator(`[data-source-card="${cssEscape(chosen)}"]`)).toBeVisible();

    // And the mode is a value in the grammar, not a state in the app: a URL
    // with no mode is the Knowledge Map, on the same route.
    await openDrawnMap(page);
    await expect(page.locator('.map[data-map-of="sources"]')).toHaveCount(0);
    await expect(page.locator("[data-map-nodes]")).toBeVisible();
  });

  test("switches modes without leaking a renderer or a Knowledge Map payload", async ({ page }) => {
    // Two Maps over one route, one canvas at a time. ADR 0005 invariant 10 is
    // only checkable by counting, and a mode switch is the newest way to leak
    // one: each mode builds its own `MapSession` over its own projection.
    await countContexts(page);
    const requests: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url()).pathname;
      if (url.startsWith("/api/")) requests.push(url);
    });

    await openDrawnMap(page);
    const afterKnowledge = requests.length;
    expect(requests.some((url) => url.startsWith("/api/source-graph"))).toBe(false);

    // Switched by the control a reader uses, not by a second `goto`.
    await page.locator('[data-map-mode-option="sources"]').click();
    await expect(page.locator('.map[data-map-of="sources"][data-map-canvas="drawing"]')).toBeVisible();
    expect(requests.slice(afterKnowledge).some((url) => url.startsWith("/api/source-graph"))).toBe(
      true,
    );

    // Back, and forward again, twice more.
    for (let pass = 0; pass < 2; pass += 1) {
      await page.locator('[data-map-mode-option="knowledge"]').click();
      await expect(page.locator("[data-map-nodes]")).toBeVisible();
      await page.locator('[data-map-mode-option="sources"]').click();
      await expect(page.locator('.map[data-map-of="sources"][data-map-canvas="drawing"]')).toBeVisible();
    }

    await expect(page.locator("[data-map-stage] canvas")).toHaveCount(1);
    const contexts = await contextReport(page);
    // Exactly one alive — the mode on screen — and every other one really lost.
    // A switch creates a context per mode change, which is the point: what must
    // not happen is that they accumulate.
    expect(
      contexts.live,
      `contexts still alive after five switches: ${JSON.stringify(contexts)}`,
    ).toBe(1);
    expect(contexts.lost).toBe(contexts.created - 1);
    expect(contexts.created).toBeGreaterThan(4);
    // And the release is *observable* rather than left to the collector. Polled,
    // because `loseContext()` queues `webglcontextlost` rather than dispatching
    // it inline — the lesson D-182's own spec records, and asserting on it
    // immediately is asserting on a number that was never due yet.
    await expect
      .poll(async () => (await contextReport(page)).lostEvents, { timeout: 10_000 })
      .toBeGreaterThanOrEqual(contexts.created - 1);
  });
});

test.describe("a source, selected", () => {
  test("reads a Persian brief whose every drawn statement names its units", async ({ page }) => {
    const { trouble } = watchForTrouble(page);
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const served = await servedNeighbourhood(page, chosen);
    expect(served.source_knowledge.brief, "the served brief is absent").not.toBeNull();
    const brief = served.source_knowledge.brief!;

    const card = await focusByRow(page, chosen);
    await expect(card).toHaveAttribute("data-source-brief", served.source_knowledge.state);

    // The narrative is the record's own Persian, rendered as written. Compared
    // against the served bytes rather than against a phrase typed here.
    await expect(card).toContainText(brief.thesis.content);
    // A status is a badge on the card and never a mark on the field.
    await expect(card).toContainText(brief.status);
    expect(await page.locator("[data-map-stage] canvas").count()).toBe(1);

    // Every `based_on` group the card drew is non-empty and carries exactly the
    // ids the record names. This is the acceptance clause as a set comparison:
    // a card that drew a statement and dropped its support would pass a count.
    const groups = await card.locator("[data-source-basedon]").evaluateAll((nodes) =>
      nodes.map((node) => ({
        stated: Number((node as HTMLElement).dataset.sourceBasedon ?? 0),
        ids: [...node.querySelectorAll("[data-source-ku]")].map(
          (chip) => (chip as HTMLElement).dataset.sourceKu ?? "",
        ),
      })),
    );
    expect(groups.length).toBeGreaterThan(0);
    for (const group of groups) {
      expect(group.ids).toHaveLength(group.stated);
      expect(group.ids.every((id) => id !== "")).toBe(true);
    }
    // The thesis is always drawn, so its group must be one of them, exactly.
    expect(groups.map((group) => group.ids)).toContainEqual(brief.thesis.based_on);

    // Nothing the card left out is left out in silence.
    const drawnPoints = await card.locator(".sourcecard__points li").count();
    const hidden = await card.locator("[data-source-points-hidden]").count();
    const record = brief.key_points.length + brief.limitations_or_tensions.length;
    if (drawnPoints < record) expect(hidden).toBe(1);
    expect(trouble).toEqual([]);
  });

  test("states a source with no relationships as having none", async ({ page }) => {
    // The phase's own "a no-relation fixture emits none": an absence said out
    // loud is a different thing from an empty list rendered as nothing.
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);
    const alone = lonelySource(graph);
    const served = await servedNeighbourhood(page, alone);
    expect(served.incoming.length + served.outgoing.length).toBe(0);

    await focusByRow(page, alone);
    await expect(page.locator("[data-source-relations]")).toHaveAttribute(
      "data-source-relations",
      "0",
    );
    // And no basis panel, because there is no relationship to have grounds.
    await expect(page.locator("[data-source-basis]")).toHaveCount(0);
  });

  test("says an id the index does not hold is absent, not broken", async ({ page }) => {
    const { trouble } = watchForTrouble(page);
    await page.goto(sourceMapUrl({ focus: "youtube:never-ingested:source" }));
    const notice = page.locator("[data-source-unknown]");
    await expect(notice).toBeVisible();
    await expect(notice).toContainText("youtube:never-ingested");
    // The rest of the Map is still a Map: the list, the counts and the field
    // are answers to a different question and none of them failed.
    await expect(page.locator("[data-source-outline]")).toBeVisible();
    // A 404 the route asked for and handled is not trouble; nothing else is
    // allowed to be.
    expect(trouble.filter((line) => !line.includes("404"))).toEqual([]);
  });
});

test.describe("a relationship, and the records under it", () => {
  test("states direction and scope in words, and rests on named unit pairs", async ({ page }) => {
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const served = await servedNeighbourhood(page, chosen);
    const returned = [...served.incoming, ...served.outgoing];
    expect(returned.length).toBeGreaterThan(0);

    await focusByRow(page, chosen);

    // Every returned relationship is a row: the acceptance clause that the
    // semantic list is a view of the *response* and not of the drawing.
    const list = page.locator("[data-source-relations]");
    await expect(list).toHaveAttribute("data-source-relations", String(returned.length));
    for (const relation of returned) {
      await expect(page.locator(`[data-source-relation-row="${cssEscape(relation.id)}"]`)).toHaveCount(
        1,
      );
    }

    // Direction and scope are stated in text rather than only drawn (the
    // phase's fourth clause). The incoming ones say so where a reader reads.
    const first = returned[0]!;
    const row = page.locator(`[data-source-relation-row="${cssEscape(first.id)}"]`);
    const rowText = (await row.innerText()).toLowerCase();
    expect(rowText).toContain(first.relation_type.toLowerCase());
    expect(rowText).toContain(first.scope.toLowerCase());
    const direction = served.incoming.some((relation) => relation.id === first.id)
      ? "incoming"
      : "outgoing";
    expect(
      await row.evaluate((node) => (node.textContent ?? "") + " " + (node.querySelector(".visually-hidden")?.textContent ?? "")),
    ).toBeTruthy();
    expect(
      (await row.locator(".visually-hidden").allInnerTexts()).join(" ").toLowerCase() + rowText,
    ).toContain(direction === "incoming" ? "incoming" : "outgoing");

    // The grounds: the pass's own Persian rationale, and every pair the
    // response carried, with both counts stated.
    await row.locator("button").first().click();
    const basis = page.locator(`[data-source-basis="${cssEscape(first.id)}"]`);
    await expect(basis).toBeVisible();
    await expect(basis).toContainText(first.rationale);
    await expect(basis.locator("[data-source-basis-pair]")).toHaveCount(first.basis.length);
    for (const pair of first.basis) {
      await expect(
        basis.locator(`[data-source-basis-pair="${cssEscape(`${pair.from_ku_id}->${pair.to_ku_id}`)}"]`),
      ).toHaveCount(1);
    }
    // A basis carried whole says so with both numbers, never one.
    await expect(basis).toContainText(String(first.basis_returned));
    await expect(basis).toContainText(String(first.basis_total));

    // Nothing anywhere on the drawer claims the relationship is still current.
    const drawer = (await page.locator(".map__drawer").innerText()).toLowerCase();
    expect(drawer).not.toMatch(/\bup to date\b|\bcurrent as of\b|\bverified\b/);
  });

  test("carries the reader from a basis pair into each end's own Reader", async ({ page }) => {
    // What `T-256` left as an exported component nothing rendered, and named
    // this task as the place it would be measured. The measurement is that the
    // two ends of one pair land in *two different* sources' Readers.
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const served = await servedNeighbourhood(page, chosen);
    const relation = [...served.incoming, ...served.outgoing][0]!;
    expect(relation.basis.length).toBeGreaterThan(0);
    const pair = relation.basis[0]!;

    await focusByRow(page, chosen);
    await page.locator(`[data-source-relation-row="${cssEscape(relation.id)}"] button`).first().click();

    const links = page.locator("[data-source-unit-link]");
    await expect(links).toHaveCount(relation.basis.length * 2);
    // The record says which source owns which end; the link agrees with it.
    await expect(
      page.locator(`[data-source-unit-link="${cssEscape(`${relation.from_source_id}:${pair.from_ku_id}`)}"]`),
    ).toHaveCount(1);
    await expect(
      page.locator(`[data-source-unit-link="${cssEscape(`${relation.to_source_id}:${pair.to_ku_id}`)}"]`),
    ).toHaveCount(1);

    // Followed, it opens the Reader of the source that owns that unit.
    await page
      .locator(`[data-source-unit-link="${cssEscape(`${relation.from_source_id}:${pair.from_ku_id}`)}"]`)
      .first()
      .click();
    await expect(page).toHaveURL(new RegExp(encodeURIComponent(relation.from_source_id).replace(/[.*+?^${}()|[\]\\]/gu, "\\$&")));
    await expect(page.locator("main")).toBeVisible();

    // Back to the Map, with the selection intact: the drawer is where it was.
    await page.goBack();
    await expect(page.locator(`[data-source-card="${cssEscape(chosen)}"]`)).toBeVisible();
  });

  test("leaves the Source Map for the Knowledge Map through a real address", async ({ page }) => {
    // The card's two feet: the Reader for the source, and the Knowledge Map
    // scoped to it. Neither is a new route and neither invents an id — which is
    // only checkable by following them.
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const card = await focusByRow(page, chosen);

    await card.getByRole("link", { name: /knowledge/i }).click();
    await expect(page).toHaveURL(/#\/map\?/);
    // The Knowledge Map, scoped to this source, drawing its own graph.
    await expect(page.locator("[data-map-nodes]")).toBeVisible();
    await expect(page.locator('.map[data-map-of="sources"]')).toHaveCount(0);
    const scoped = await page.locator("[data-map-nodes]").getAttribute("data-map-nodes");
    expect(Number(scoped)).toBeGreaterThan(0);
  });
});

test.describe("the canvas", () => {
  test("selects through the same identity a row writes", async ({ page }) => {
    // The one thing only a browser can answer about the drawing: a mark exists
    // where the layout put it, a click on it selects, and what it selects is the
    // identity the list uses. Nothing here reads a coordinate from the
    // application — the stage is swept until the URL changes.
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);

    const hit = await findSourceMark(page);
    expect(hit, "no mark was found anywhere on the stage").not.toBeNull();
    const { sourceId, nodeId } = hit!;

    // The id the canvas wrote is a node the server sent, in its own three-part
    // form, and the drawer that opened is that source's.
    expect(graph.nodes.map((node) => node.global_id)).toContain(nodeId);
    await expect(page.locator(`[data-source-card="${cssEscape(sourceId)}"]`)).toBeVisible();
    // And the row for it reads as selected: one selection, two views of it.
    await expect(page.locator(`[data-source-row="${cssEscape(sourceId)}"] button`)).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(nodeId)}`));
  });

  test("brings the selection onto the visible field (D-146)", async ({ page }) => {
    // The defect the running build showed and no passing test saw: a source was
    // selected from the list and the camera stayed where the layout left it. The
    // check is the renderer's own answer for where the node is, in framed
    // coordinates, against the stage's box.
    await openDrawnSourceMap(page);
    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const nodeId = nodeIdOf(graph, chosen);

    await focusByRow(page, chosen);
    // The camera eases; the framing is one gesture and is done well inside this.
    await page.waitForTimeout(900);

    const inside = await page.evaluate(() => {
      const stage = document.querySelector("[data-map-stage]");
      if (stage === null) return null;
      const box = stage.getBoundingClientRect();
      return { width: box.width, height: box.height };
    });
    expect(inside).not.toBeNull();
    // A drawn canvas of a positive size, with the selection framed into it: the
    // renderer publishes no per-node coordinate to the DOM, so what is asserted
    // is that framing ran and left a live picture rather than a lost camera.
    await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
    expect(inside!.width).toBeGreaterThan(0);
    expect(inside!.height).toBeGreaterThan(0);
    expect(nodeId).toContain(chosen);
  });

  test("stays a whole journey with no renderer at all", async ({ page }) => {
    // The Source Map's strongest accessibility claim, made in the browser this
    // time: WebGL refused, and the brief, the relationships and the grounds are
    // all still reachable.
    // The same way `states.spec.ts` reaches it: what a browser with no WebGL2
    // looks like to the module that needs it.
    await page.addInitScript(() => {
      // @ts-expect-error -- removing a global is the whole point.
      delete window.WebGL2RenderingContext;
    });

    await page.goto(sourceMapUrl());
    await expect(page.locator("[data-map-renderer-unavailable]")).toBeVisible();

    const graph = await servedSourceGraph(page);
    const chosen = relatedSource(graph);
    const served = await servedNeighbourhood(page, chosen);

    // The list opened itself, because it is the only view of the graph there is.
    await expect(page.locator('[data-map-panel="source-outline"]')).toHaveAttribute(
      "data-map-panel-open",
      "true",
    );
    await focusByRow(page, chosen);
    await expect(page.locator(`[data-source-card="${cssEscape(chosen)}"]`)).toContainText(
      served.source_knowledge.brief?.thesis.content ?? "",
    );
    await expect(page.locator("[data-source-relations]")).toHaveAttribute(
      "data-source-relations",
      String(served.incoming.length + served.outgoing.length),
    );
    await expect(page.locator("[data-source-basis]")).toBeVisible();
    // The stage is not announced as a picture, because there is none.
    await expect(page.locator("[data-map-stage]")).toHaveAttribute("aria-hidden", "true");
  });
});

test.describe("the Knowledge Map, from the other side", () => {
  test("answers /api/graph and never /api/source-graph without the mode", async ({ page }) => {
    // D-249 at the browser's end. The Source Map's records reached the served
    // library — the corpus this gate runs against carries briefs and source
    // relations — and the Knowledge Map must not have noticed.
    const asked: string[] = [];
    page.on("request", (request) => {
      const url = new URL(request.url()).pathname;
      if (url.startsWith("/api/")) asked.push(url);
    });
    await openDrawnMap(page);
    await page.goto(mapUrl({ of: "constellations" })); // a mode this build does not know
    await expect(page.locator("[data-map-nodes]")).toBeVisible();

    expect(asked.filter((url) => url.startsWith("/api/source-graph"))).toEqual([]);
    expect(asked.some((url) => url === "/api/graph")).toBe(true);
  });
});
