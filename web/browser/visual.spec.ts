/**
 * The visual-quality gate (`T-215`, ADR 0006 clause 5, D-154).
 *
 * `T-209` walked the route and proved it *behaves*. ADR 0006 exists because a
 * green walk said nothing about what the screen looked like: the review that
 * opened Phase 2.1 rejected a Map every behavioural test passed over. So this
 * file asks the other question, per scenario, and it asks it in the two ways
 * a composition can be wrong.
 *
 * **Geometry, asserted.** Not a second implementation of `measure_orbit.ts` --
 * `browser/composition.ts` is that script's probe, moved, and both callers read
 * the same numbers. What is here is what a *scenario* makes of them: which of
 * SPEC §5's three compositions the field holds, that placed plus counted equals
 * the neighbours the server returned, that no card is clipped, that no two
 * marks share a pixel, that nothing sits under a floating control, that every
 * relation pill is horizontal and seated, that the floating chrome covers no
 * more of the field than the approved captures spend on it at that tier
 * (`T-216`), and that the document is still the viewport (D-153).
 *
 * **Pictures, produced.** Every scenario writes a PNG to
 * `docs/mockups/T-215/captures/`, the same shape and the same names as
 * `capture_mockups.ts` writes the approved sources to
 * `docs/mockups/T-211/captures/`. `T-215`'s acceptance is a person comparing
 * the two sets; the assertions below are what makes that comparison worth
 * making rather than a look at whatever the build happened to draw. The
 * directory is gitignored for the reason the mockups' is: a capture is a build
 * product of committed sources, and `capture_mockups.ts` regenerates the
 * reference on demand (D-191).
 *
 * **What this gate cannot see, stated rather than implied.** ADR 0006 clause 5
 * also forbids a graph label under a card. In the production Map that label is
 * drawn by WebGL into the single stage canvas -- there is no DOM node for it,
 * no per-label geometry to read, and Sigma exposes no instance to ask -- so the
 * clause is asserted where it *is* readable: `labelPolicy.ts` hides a carded
 * node's label and an edge's label when both its endpoints are carded, and
 * `labelPolicy.test.ts` and `visualSystem.test.ts` hold it. What this file
 * asserts is the half that has a rectangle: a relation *pill* is a label too,
 * and a pill over a card is the same defect with a DOM node to name it.
 *
 * The scenarios are pointed at the served library, whichever one that is: the
 * numbers come from the payload, never from a constant, which is the discipline
 * `gate.ts` is built on and what lets the same file run over the committed
 * fixtures and over the real 86-node library.
 */

import { expect, test, type Browser, type Page } from "@playwright/test";

import { measureComposition, summarise, type CompositionReport } from "./composition";
import { busiest, mapUrl, openPanel, servedGraph, settledStage, watchForTrouble } from "./gate";

/** The review viewport ADR 0006 and SPEC are both specified against. */
const REVIEW = { width: 2852, height: 1688 };

/**
 * How much of the field floating chrome may cover, per tier (`T-216`, D-203).
 *
 * The clause `T-216` adds, and the one number in this file that is *read off
 * the approved captures* rather than measured on the build:
 * `scripts/capture_mockups.ts` prints the share for every reference picture,
 * with `composition.ts`'s own `coveredShare`, so the reference and the build
 * are measured by one implementation. What it printed:
 *
 * | Tier | Approved Explore | Approved Focus | This build, worst |
 * |---|---|---|---|
 * | `full` (2852x1688) | 2.7 % | 19.8 % | 11.9 % |
 * | `compact` (1440x900) | 10.3 % | 6.4 % | 27.3 % |
 * | `stack` (390x844) | — | 8.8 % | 0 % |
 *
 * `full` and `stack` are the approved measurement, rounded up: a fifth of the
 * field is the most chrome the approved set ever puts on one, and this build
 * is comfortably inside it.
 *
 * **`compact` is not, and the reason is recorded rather than smoothed over.**
 * This build spends 27.3 % there, against the reference's 10.3 %, and the gap
 * is not slack: at that tier the drawer floats *over* the field instead of
 * taking a slice out of it, and the chrome's rectangles are what
 * `placeConstellation` refuses cards against -- so the share and the recorded
 * card counts are one number seen twice. Measured, not assumed: bounding these
 * surfaces to 14.4 % of the field placed **three** cards at 1440x900 where
 * `T-213` recorded two, and `T-216` states that the recorded numbers must not
 * change. So the `compact` bound is a ratchet a little above today's worst
 * rather than the reference's own share, the difference between the two is a
 * finding for the acceptance (`SPEC.md` §17), and the trade it names is
 * explicit: the reference's 10.3 % costs the 2 / 6 this gate holds.
 *
 * **The instrument that derives them does not run in CI** (D-203). D-201 says
 * these are "read off the reference by the instrument that measures the
 * build", and that is true: `capture_mockups.ts` calls the very same
 * `coveredShare` over the mockups' own surfaces and prints it beside every
 * reference capture. What no job does is *re-run* it — `capture_baseline.ts`
 * and `measure_orbit.ts` are manual — so nothing would notice these three
 * numbers drifting away from the reference they were derived from.
 *
 * What CI does check is the half that protects a reader: that this build stays
 * inside them. Re-deriving the reference's own share needs the approved
 * captures and a browser, so it stays a manual step
 * (`npm run mockups:baseline`, `npm run measure:orbit`, both named in
 * `web/README.md`). The gap is stated here rather than left to be inferred
 * from a job list.
 */
const CHROME_SHARE_BOUND: Record<"full" | "compact" | "stack", number> = {
  full: 0.2,
  compact: 0.3,
  stack: 0.1,
};

/** The two breakpoints the Phase 2 gate already tests. */
const DESKTOP = { width: 1440, height: 900 };
const LAPTOP = { width: 1280, height: 720 };
const PHONE = { width: 390, height: 844 };

/**
 * The entity the approved compositions are of (`SPEC.md` §11).
 *
 * `T-215`'s question is whether the running build reproduces *those pictures*,
 * and two pictures of two different neighbourhoods cannot answer it: the
 * mockups compose `KU-000028`, degree 8, an asymmetric fan-out chosen because
 * a balanced one would hide the layout problem. So the scenarios walk it
 * whenever the served library holds it, and fall back to the busiest entity
 * the served graph has when it does not -- which is what the committed
 * fixtures are, and where the clauses still hold even though the numbers in
 * §14 cannot.
 */
// The one Node global this spec needs, declared where it is used exactly as
// `playwright.config.ts` and `vite.config.ts` already do: this project installs
// no ambient Node types (R17, `browser/tsconfig.json`).
declare const process: { env: Record<string, string | undefined> };

const MOCKUP_CENTRE = "youtube:pqlWNihgdjI:KU-000028";

function centreOf(graph: Awaited<ReturnType<typeof servedGraph>>): string {
  return graph.nodes.some((node) => node.global_id === MOCKUP_CENTRE)
    ? MOCKUP_CENTRE
    : busiest(graph);
}

/** Where the captures land, beside the approved sources they are compared with. */
function capturesDir(): string {
  return `${test.info().project.testDir}/../../docs/mockups/T-215/captures`;
}

interface Scenario {
  /** The capture's name, which is also the test's. */
  readonly name: string;
  readonly viewport: { width: number; height: number };
  readonly colorScheme?: "dark" | "light";
  /** Persian, set the way a reader sets it: the stored preference. */
  readonly locale?: "fa";
  readonly reducedMotion?: "reduce";
  readonly hasTouch?: boolean;
  /** Whether something is selected, and therefore whether there is an orbit. */
  readonly focused: boolean;
  /** Which composition SPEC §5 says this field can hold. */
  readonly tier: "full" | "compact" | "stack";
  /** Run a search first, so the drawer in the capture has results in it. */
  readonly search?: boolean;
  /**
   * What `T-213` measured on the mockups' own neighbourhood at this viewport
   * (`SPEC.md` §14, D-193). Asserted only when that entity is the one served:
   * "anything worse is a regression and anything better wants explaining", and
   * a number measured on another library is neither.
   */
  readonly recorded?: { readonly placed: number; readonly counted: number };
}

/**
 * The matrix ADR 0006's Validation section asks to be walked: both
 * compositions, in dark and light, in English and Persian, at the review
 * viewport and at the tested breakpoints, with a coarse pointer and with
 * reduced motion.
 */
const SCENARIOS: readonly Scenario[] = [
  { name: "explore-dark", viewport: REVIEW, colorScheme: "dark", focused: false, tier: "full" },
  { name: "explore-light", viewport: REVIEW, colorScheme: "light", focused: false, tier: "full" },
  {
    name: "explore-fa",
    viewport: REVIEW,
    colorScheme: "dark",
    locale: "fa",
    focused: false,
    tier: "full",
  },
  {
    name: "focus-dark",
    viewport: REVIEW,
    colorScheme: "dark",
    focused: true,
    tier: "full",
    recorded: { placed: 7, counted: 1 },
  },
  {
    name: "focus-light",
    viewport: REVIEW,
    colorScheme: "light",
    focused: true,
    tier: "full",
    recorded: { placed: 7, counted: 1 },
  },
  {
    name: "focus-fa",
    viewport: REVIEW,
    colorScheme: "dark",
    locale: "fa",
    focused: true,
    tier: "full",
    recorded: { placed: 7, counted: 1 },
  },
  {
    name: "focus-search",
    viewport: REVIEW,
    colorScheme: "dark",
    focused: true,
    tier: "full",
    search: true,
    // Six, not seven, and measured rather than assumed: a search rail with
    // results in it grows from 237 px to 424 px, the orbit keeps its cards
    // clear of the chrome, and the card that fitted beside the collapsed rail
    // is refused and *counted* -- `no_room` goes from 1 to 2. Nothing is
    // silently dropped, which is the clause that matters; what the reviewer
    // should know is that reading and searching are two compositions, and
    // this is the second one's number (`SPEC.md` §16).
    recorded: { placed: 6, counted: 2 },
  },
  {
    name: "focus-reduced-motion",
    viewport: REVIEW,
    colorScheme: "dark",
    reducedMotion: "reduce",
    focused: true,
    tier: "full",
    recorded: { placed: 7, counted: 1 },
  },
  { name: "explore-1440", viewport: DESKTOP, colorScheme: "dark", focused: false, tier: "compact" },
  {
    name: "focus-1440",
    viewport: DESKTOP,
    colorScheme: "dark",
    focused: true,
    tier: "compact",
    recorded: { placed: 2, counted: 6 },
  },
  { name: "focus-1280", viewport: LAPTOP, colorScheme: "dark", focused: true, tier: "compact" },
  {
    name: "focus-390",
    viewport: PHONE,
    colorScheme: "dark",
    hasTouch: true,
    focused: true,
    tier: "stack",
  },
];

/** One scenario's page, opened and settled, with its trouble log watching. */
async function openScenario(
  browser: Browser,
  scenario: Scenario,
): Promise<{
  page: Page;
  graph: Awaited<ReturnType<typeof servedGraph>>;
  centre: string;
  trouble: string[];
  close: () => Promise<void>;
}> {
  const context = await browser.newContext({
    viewport: scenario.viewport,
    colorScheme: scenario.colorScheme ?? "dark",
    deviceScaleFactor: 1,
    ...(scenario.reducedMotion === undefined ? {} : { reducedMotion: scenario.reducedMotion }),
    ...(scenario.hasTouch === undefined ? {} : { hasTouch: scenario.hasTouch }),
  });
  const page = await context.newPage();
  const { trouble } = watchForTrouble(page);
  if (scenario.locale === "fa") {
    // The Shell reads the stored preference on its first render, so it is set
    // before the bundle runs rather than switched afterwards: a locale changed
    // after the layout would capture a composition laid out in one direction
    // and then mirrored.
    await page.addInitScript(() => {
      window.localStorage.setItem("x2knwldg.locale", "fa");
    });
  }

  // Asked over this page's own request context, before anything is navigated
  // to: which entity is walked is a fact about the served library, never a
  // constant typed into a test.
  const graph = await servedGraph(page);
  const centre = centreOf(graph);

  await page.goto(mapUrl(scenario.focused ? { focus: centre } : {}));
  await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
  await expect(page.locator("[data-map-stage] canvas")).toHaveCount(1);
  if (scenario.focused) {
    if (scenario.tier === "stack") {
      // No orbit below the `compact` minimum: the route keeps its document
      // composition, so there is no primary card to wait for and the drawer's
      // own arrival is what says the selection landed.
      await expect(page.locator("[data-map-quickread]")).toBeVisible();
    } else {
      await settledStage(page);
    }
  }
  return { page, graph, centre, trouble, close: () => context.close() };
}

/** The picture this scenario is for, written where a reviewer will look for it. */
async function capture(page: Page, name: string): Promise<void> {
  const file = `${capturesDir()}/${name}.png`;
  await page.screenshot({ path: file, fullPage: false });
  test.info().annotations.push({ type: "capture", description: file });
}

/**
 * The neighbourhood the route was answered with, and what it implies about
 * the composition.
 *
 * Hops are a breadth-first walk of the returned edges, **undirected**, which
 * is `neighbourhood.ts`'s own rule: a relation is a connection whichever way
 * the index stored it. The side is the other half -- the direction of the
 * first relation joining a neighbour to the centre, in the order the related
 * list sorts them, seen *from the centre*. That inversion is the whole subject
 * of one of `T-213`'s five departures: reading the direction from the
 * neighbour's end put every card on the wrong half of the field, and a suite
 * of 607 green tests said nothing about it.
 */
async function neighbourhood(
  page: Page,
  centre: string,
  depth: number,
): Promise<{ hops: Map<string, number>; sides: Map<string, string>; returned: string[] }> {
  const response = await page.request.get(
    `/api/graph/neighborhood/${encodeURIComponent(centre)}?depth=${depth}&limit=200`,
  );
  expect(response.ok()).toBe(true);
  const body = (await response.json()) as {
    data: {
      center_id: string;
      nodes: { global_id: string }[];
      edges: { id: string; from_id: string; to_id: string; relation: string }[];
    };
  };
  const { nodes, edges, center_id: centreId } = body.data;

  const hops = new Map<string, number>([[centreId, 0]]);
  let frontier = [centreId];
  for (let distance = 1; frontier.length > 0; distance += 1) {
    const next: string[] = [];
    for (const edge of edges) {
      for (const [near, far] of [
        [edge.from_id, edge.to_id],
        [edge.to_id, edge.from_id],
      ]) {
        if (near === undefined || far === undefined) continue;
        if (!frontier.includes(near) || hops.has(far)) continue;
        hops.set(far, distance);
        next.push(far);
      }
    }
    frontier = next;
  }

  const sides = new Map<string, string>();
  for (const node of nodes) {
    if (node.global_id === centreId) continue;
    const joining = edges
      .filter(
        (edge) =>
          (edge.from_id === node.global_id && edge.to_id === centreId) ||
          (edge.to_id === node.global_id && edge.from_id === centreId),
      )
      .sort((left, right) =>
        left.relation === right.relation
          ? left.id < right.id
            ? -1
            : 1
          : left.relation < right.relation
            ? -1
            : 1,
      );
    const first = joining[0];
    if (first === undefined) continue;
    // Seen from the focus: a record that runs *into* it is incoming, and
    // incoming reads first, so it belongs on the inline start.
    sides.set(node.global_id, first.from_id === node.global_id ? "incoming" : "outgoing");
  }

  return {
    hops,
    sides,
    returned: nodes.map((node) => node.global_id).filter((id) => id !== centreId),
  };
}

/** The clauses every composition owes, whatever tier it is and whatever is on it. */
function expectNothingCollides(report: CompositionReport): void {
  expect(report.clipped, "a mark left the field").toEqual([]);
  expect(report.collided, "two marks share pixels").toEqual([]);
  expect(report.covered, "a mark sits under a floating control").toEqual([]);
  expect(report.crowded, "a relation pill found no clear seat").toEqual([]);
  expect(report.rotated, "a relation pill's text is not horizontal").toEqual([]);
}

/**
 * The field is mostly graph: floating chrome stays inside the tier's bound.
 *
 * `T-216`'s clause, and it is a *share* rather than a list of rectangles on
 * purpose -- the failure it exists to catch is not one oversized panel but
 * four honest ones adding up, which is what `T-215`'s comparison found at the
 * `compact` tier and what no per-surface rule would have reported.
 */
function expectChromeFitsTheField(report: CompositionReport, tier: Scenario["tier"]): void {
  expect(
    report.chromeShare,
    `floating chrome covers ${(report.chromeShare * 100).toFixed(1)} % of the ` +
      `${tier} field, over the ${(CHROME_SHARE_BOUND[tier] * 100).toFixed(0)} % ` +
      "the approved captures set for it",
  ).toBeLessThanOrEqual(CHROME_SHARE_BOUND[tier]);
}

test.describe("the composition, scenario by scenario", () => {
  for (const scenario of SCENARIOS) {
    test(scenario.name, async ({ browser }) => {
      const opened = await openScenario(browser, scenario);
      const { page, graph, centre, trouble } = opened;
      try {
        if (scenario.search === true) {
          // A word the served library actually holds, so the drawer in the
          // capture has real results rather than an empty state.
          const record = graph.nodes.find((node) => node.global_id === centre);
          const word =
            (record?.label ?? "").split(/\s+/u).find((token) => token.length > 5) ?? "the";
          const rail = await openPanel(page, "search");
          await rail.getByRole("searchbox").fill(word);
          await rail.getByRole("button", { name: "Search", exact: true }).click();
          await expect(rail.locator("[data-map-result]").first()).toBeVisible();
        }

        const report = await measureComposition(page);
        test.info().annotations.push({ type: "composition", description: summarise(report) });
        await capture(page, scenario.name);

        // The tier is read from the route rather than inferred from a card
        // count, which is the seam `T-213` published for exactly this.
        expect(report.tier).toBe(scenario.tier);
        expect(report.direction).toBe(scenario.locale === "fa" ? "rtl" : "ltr");
        expectNothingCollides(report);
        expectChromeFitsTheField(report, scenario.tier);

        // The workspace clause: the graph occupies the route's viewport and
        // the document does not scroll (D-153). The `stack` tier is the one
        // deliberate exception -- below 900 px the route is its own document,
        // which is `T-213`'s fifth departure and is recorded as such.
        if (scenario.tier === "stack") {
          expect(report.documentHeight).toBeGreaterThanOrEqual(scenario.viewport.height);
        } else {
          expect(report.documentHeight).toBe(scenario.viewport.height);
        }

        if (!scenario.focused) {
          // Explore is the quiet overview: no orbit, no cards, and the picture
          // is the graph rather than a diagram over it.
          expect(report.centre).toBeNull();
          expect(report.cards).toEqual([]);
          expect(report.orbitTier).toBeNull();
          expect(trouble).toEqual([]);
          return;
        }

        // Focus, at a tier that has an orbit at all.
        if (scenario.tier === "stack") {
          expect(report.orbitTier).toBeNull();
          expect(trouble).toEqual([]);
          return;
        }

        expect(report.orbitTier).toBe(scenario.tier);
        expect(report.centre).toBe(centre);

        const served = await neighbourhood(page, centre, report.depth);
        // R20's accounting, per scenario: every neighbour is carded or counted
        // with a reason, and the two numbers come from one settled placement.
        expect(report.returned).toBe(served.returned.length);
        expect(report.placed + report.omittedTotal).toBe(report.returned);
        await expect(page.locator("[data-map-related-entity]")).toHaveCount(report.returned);

        /*
         * The numbers `T-213` recorded, held: 7 placed and 1 counted at the
         * review viewport, 2 and 6 at 1440x900, in every mode -- a light
         * theme and a Persian one place the same cards, because the boxes the
         * placement reserves are the tier's rather than the text's.
         *
         * These assert only against the mockups' own centre, and that is a
         * fact about the *library* rather than about the code: `KU-000028`'s
         * asymmetric degree-8 fan-out is what the compositions were composed
         * over, and no tracked fixture holds it because `output/` is
         * gitignored. Six of the sixteen scenarios carry recorded numbers, so
         * on the committed fixtures the numeric half of six scenarios cannot
         * run.
         *
         * What changed is that it no longer *silently* does not run. The docs
         * call this "the regression net", and a net whose numeric half is
         * quietly absent on every machine but one is not one. The skip is now
         * stated in the report — `annotations` reach the list and GitHub
         * reporters both — and `X2KNWLDG_BROWSER_REQUIRE_RECORDED=1` turns it
         * into a failure, which is what a run over the real library should
         * set. The geometry invariants above and below are unconditional and
         * always were.
         */
        if (scenario.recorded !== undefined) {
          if (centre === MOCKUP_CENTRE) {
            expect(report.placed, "fewer cards than T-213 measured").toBe(
              scenario.recorded.placed,
            );
            expect(report.omittedTotal, "more counted than T-213 measured").toBe(
              scenario.recorded.counted,
            );
          } else {
            const why =
              `the recorded acceptance numbers (${scenario.recorded.placed} placed, ` +
              `${scenario.recorded.counted} counted) were not checked: this library ` +
              `does not serve ${MOCKUP_CENTRE}, the centre the compositions were ` +
              `composed over, so the walk fell back to ${centre}`;
            test.info().annotations.push({ type: "recorded-numbers-skipped", description: why });
            console.warn(`[${scenario.name}] ${why}`);
            expect(
              process.env.X2KNWLDG_BROWSER_REQUIRE_RECORDED,
              `${why}. Set X2KNWLDG_BROWSER_REQUIRE_RECORDED=1 only where the ` +
                "library serves that entity.",
            ).not.toBe("1");
          }
        }

        const field = report.field;
        expect(field, "the scenario has no field to measure").not.toBeNull();
        const stage = field as NonNullable<typeof field>;
        const primary = report.cards.find((card) => card.primary);
        expect(primary, "nothing is the centre of this orbit").toBeDefined();
        const focused = primary as NonNullable<typeof primary>;

        for (const card of report.cards) {
          if (card.primary) {
            expect(card.side).toBe("centre");
            expect(card.hops).toBe(0);
            continue;
          }

          // The composition states a hop count and a direction; both are the
          // records', and this is where that is checked rather than trusted.
          expect(card.hops, `${card.id} is carded at the wrong hop`).toBe(
            served.hops.get(card.id),
          );
          const stated = served.sides.get(card.id);
          if (card.hops === 1 && stated !== undefined) {
            expect(card.side, `${card.id} is on the wrong side of the focus`).toBe(stated);
          }

          // And the side is a *place*: incoming reads first, so it is the
          // inline start -- the left in English, the right in Persian.
          const middle = (card.rect.left + card.rect.right) / 2;
          const towardsStart = report.direction === "rtl" ? middle > stage.left + stage.width / 2 : middle < stage.left + stage.width / 2;
          expect(
            towardsStart,
            `${card.id} is ${card.side} but drawn on the ${towardsStart ? "start" : "end"} side`,
          ).toBe(card.side === "incoming");

          // The focused card is the unmistakable centre: every neighbour's
          // card is smaller than it, which is the first of the four means
          // SPEC §6 gives for saying so.
          expect(card.rect.width * card.rect.height).toBeLessThan(
            focused.rect.width * focused.rect.height,
          );
        }

        // ... and it is nearer the middle of the field than anything else on it.
        const distanceTo = (rect: { left: number; right: number; top: number; bottom: number }) =>
          Math.hypot(
            (rect.left + rect.right) / 2 - (stage.left + stage.width / 2),
            (rect.top + rect.bottom) / 2 - (stage.top + stage.height / 2),
          );
        for (const card of report.cards) {
          if (card.primary) continue;
          expect(distanceTo(focused.rect)).toBeLessThan(distanceTo(card.rect));
        }

        expect(trouble).toEqual([]);
      } finally {
        await opened.close();
      }
    });
  }
});

test.describe("the workspace at the review viewport", () => {
  test("walks search, focus and Quick Read without ever scrolling the document", async ({
    browser,
  }) => {
    // ADR 0006 clause 4, as a walk rather than a measurement: the journey the
    // baseline needed a 5795 px document for has to happen inside 1688 px of
    // screen. Every step asserts the document is still the viewport, because
    // a surface that opens by making the page taller has already failed.
    const context = await browser.newContext({
      viewport: REVIEW,
      colorScheme: "dark",
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    const { trouble } = watchForTrouble(page);
    try {
      const graph = await servedGraph(page);
      const centre = busiest(graph);
      const record = graph.nodes.find((node) => node.global_id === centre);

      const height = async () =>
        page.evaluate(() => ({
          document: document.documentElement.scrollHeight,
          scrolled: window.scrollY,
        }));

      await page.goto(mapUrl());
      await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();
      expect(await height()).toEqual({ document: REVIEW.height, scrolled: 0 });

      const word = (record?.label ?? "").split(/\s+/u).find((token) => token.length > 5) ?? "the";
      const rail = await openPanel(page, "search");
      await rail.getByRole("searchbox").fill(word);
      await rail.getByRole("button", { name: "Search", exact: true }).click();
      const results = rail.locator("[data-map-result]");
      await expect(results.first()).toBeVisible();
      expect(await height()).toEqual({ document: REVIEW.height, scrolled: 0 });

      await results.first().locator("[data-map-focus-action]").click();
      await expect(page.locator("[data-map-quickread]")).toBeVisible();
      await settledStage(page);
      expect(await height()).toEqual({ document: REVIEW.height, scrolled: 0 });

      // Every surface the journey uses is on screen while it is used, and
      // every one of them is reachable without moving the document.
      //
      // Two clauses, because the first one alone is false and this run proved
      // it: the related list at the review viewport is 1952 px of content --
      // the whole neighbourhood, which R20 requires it to hold -- inside a
      // 1559 px drawer. A list taller than the viewport is not the failure
      // D-153 names; a list taller than the *surface it lives in* that the
      // surface will not scroll is, because then the rows past the fold can
      // be reached by nothing at all. So the surface a reader operates is
      // asserted to be wholly on screen, and content longer than it is
      // asserted to have its own scroll -- which is exactly what `T-213`'s
      // fifth departure bounded these panels for.
      for (const surface of [
        "[data-map-panel='search']",
        "[data-map-quickread]",
        "[data-map-panel='related']",
        "[data-map-nodes]",
      ]) {
        const box = await page.locator(surface).first().boundingBox();
        expect(box, `${surface} has no box at the review viewport`).not.toBeNull();
        const seen = box as NonNullable<typeof box>;
        expect(seen.y, `${surface} starts above the viewport`).toBeGreaterThanOrEqual(0);
        expect(seen.y, `${surface} starts below the fold`).toBeLessThan(REVIEW.height);

        const holder = await page.locator(surface).first().evaluate((element) => {
          const host = element.closest("[data-map-chrome]");
          if (host === null) return null;
          const rect = host.getBoundingClientRect();
          const style = getComputedStyle(host);
          return {
            name: host.className,
            top: rect.top,
            bottom: rect.bottom,
            scrollHeight: host.scrollHeight,
            clientHeight: host.clientHeight,
            overflow: style.overflowY,
          };
        });
        expect(holder, `${surface} floats on nothing`).not.toBeNull();
        const chrome = holder as NonNullable<typeof holder>;
        expect(chrome.top, `${chrome.name} starts above the viewport`).toBeGreaterThanOrEqual(-0.5);
        expect(
          chrome.bottom,
          `${chrome.name} runs past the fold at the review viewport`,
        ).toBeLessThanOrEqual(REVIEW.height + 0.5);
        if (chrome.scrollHeight > chrome.clientHeight + 1) {
          expect(
            chrome.overflow,
            `${chrome.name} holds more than it shows and will not scroll`,
          ).toMatch(/auto|scroll/);
        }
      }

      expect(trouble).toEqual([]);
    } finally {
      await context.close();
    }
  });

  test("keeps the composition when the reader arrives by keyboard alone", async ({ browser }) => {
    // The same field, reached with no pointer at all: the orbit is drawn from
    // a selection, and a selection made by keyboard is the same selection
    // (D-153's last sentence, and `T-209`'s access walk one composition on).
    const context = await browser.newContext({
      viewport: REVIEW,
      colorScheme: "dark",
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    try {
      const graph = await servedGraph(page);
      await page.goto(mapUrl());
      await expect(page.locator('.map[data-map-canvas="drawing"]')).toBeVisible();

      const outline = await openPanel(page, "outline");
      const action = outline.locator("[data-map-focus-action]").first();
      const chosen = await action.getAttribute("data-map-focus-action");
      await action.focus();
      // Pressed, not clicked: the whole subject is the keyboard path.
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`focus=${encodeURIComponent(chosen ?? "")}`));
      await settledStage(page);

      const report = await measureComposition(page);
      test.info().annotations.push({ type: "composition", description: summarise(report) });
      await capture(page, "focus-keyboard");
      expect(report.centre).toBe(chosen);
      expect(report.tier).toBe("full");
      expectNothingCollides(report);
      expectChromeFitsTheField(report, "full");
      expect(report.documentHeight).toBe(REVIEW.height);
      // The focus ring is on the control that was pressed, not lost to the
      // camera gesture that followed it.
      const active = await page.evaluate(
        () => document.activeElement?.getAttribute("data-map-focus-action") ?? null,
      );
      expect(active).toBe(chosen);
      expect(graph.nodes.some((node) => node.global_id === chosen)).toBe(true);
    } finally {
      await context.close();
    }
  });
});

test.describe("the states, at the review viewport", () => {
  test("stays a workspace with no renderer at all", async ({ browser }) => {
    // The state `states.spec.ts` proves is *stated*; this one asks what it
    // looks like. A route whose picture is impossible still has to be a
    // workspace rather than a column of panels the reader scrolls.
    const context = await browser.newContext({
      viewport: REVIEW,
      colorScheme: "dark",
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    try {
      await page.addInitScript(() => {
        // @ts-expect-error -- removing a global is the whole point.
        delete window.WebGL2RenderingContext;
      });
      await page.goto(mapUrl());
      await expect(page.locator("[data-map-renderer-unavailable]")).toBeVisible();
      await capture(page, "states-unavailable");

      const report = await measureComposition(page);
      test.info().annotations.push({ type: "composition", description: summarise(report) });
      expect(report.documentHeight).toBe(REVIEW.height);
      expect(report.cards).toEqual([]);
      expectNothingCollides(report);
      // A route that cannot draw is the case that most needs this bound: the
      // counts open themselves (D-129) and the notice takes the middle of the
      // field, and the surface a reader is left with is still a workspace.
      expectChromeFitsTheField(report, "full");
    } finally {
      await context.close();
    }
  });

  test("states a partial graph on the field rather than under it", async ({ browser }) => {
    // A page the server answered and a page it refused, which is the pair
    // D-139 exists for -- captured here because "partial" is a *picture* as
    // well as a sentence, and the sentence has to be on screen without
    // scrolling like everything else.
    const context = await browser.newContext({
      viewport: REVIEW,
      colorScheme: "dark",
      deviceScaleFactor: 1,
    });
    const page = await context.newPage();
    try {
      let answered = 0;
      await page.route("**/api/graph?**", async (route) => {
        const url = new URL(route.request().url());
        url.searchParams.set("limit", "5");
        answered += 1;
        if (answered > 1) return route.fulfill({ status: 503, body: "{}" });
        await route.continue({ url: url.toString() });
      });
      await page.goto(mapUrl());
      await expect(page.locator("[data-map-nodes]")).toBeVisible();
      await capture(page, "states-partial");

      const report = await measureComposition(page);
      test.info().annotations.push({ type: "composition", description: summarise(report) });
      expect(report.documentHeight).toBe(REVIEW.height);
      expectNothingCollides(report);
      expectChromeFitsTheField(report, "full");
    } finally {
      await context.close();
    }
  });
});
