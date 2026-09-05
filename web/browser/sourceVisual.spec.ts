/**
 * The Source Map's visual gate and screenshot review (`T-257`).
 *
 * `visual.spec.ts` is the Knowledge Map's half of this and its shape is
 * inherited whole: geometry asserted per scenario, pictures written where a
 * reviewer will look for them, and every number read off the payload the page
 * was answered with. What is different is *what there is to measure*, and that
 * difference is this file's first job to state honestly.
 *
 * **The production Focus is not the approved Focus, and this is where that is
 * recorded (D-283).** `T-255`'s approved compositions drew a Directional Orbit
 * around the focused source: neighbour cards seated on the field, relation pills
 * riding their edges, incoming on the side reading starts from. `T-256` built
 * something else — one readable card and every relationship as a row, both in
 * the end rail's drawer — and the `git diff` that proves the Knowledge Map did
 * not move (D-278) is the same diff that shows `MapOrbit`, `constellation.ts`
 * and `placeOrbit` were never called from this view. So the orbit clauses of
 * ADR 0006 clause 5 — no card clipped, no two cards over the same pixels, every
 * pill horizontal and seated — have **no subject on this surface**: there are no
 * cards on the field to clip, collide or cover.
 *
 * That is not a gap this gate can close by asserting harder. It is a scope
 * difference between an approved mockup and a built surface, and the honest
 * response is to say which clauses transferred and which have nothing to bind
 * to, rather than to run an orbit measurement that trivially passes over an
 * empty set and report it as a green orbit. What *does* transfer is every clause
 * about the field and the floats, and those are asserted below:
 *
 * - the tier the measured field holds, read from the route's own seam;
 * - the direction, mirrored rather than restyled;
 * - no two floating surfaces over the same pixels;
 * - the chrome's share of the field, against the approved captures' own numbers;
 * - the document is the viewport and does not scroll (D-153);
 * - and the drawer is reachable to its foot, which is the one defect the running
 *   build showed `T-256` and which no test could have failed on.
 *
 * The captures go to `docs/mockups/T-257/captures/`, gitignored for the reason
 * every other capture directory is: a picture is a build product of committed
 * sources, and a stored PNG is a thing that can quietly stop being true.
 */

import { expect, test, type Browser, type Page } from "@playwright/test";

import { summarise as summariseKnowledge } from "./composition";
import { watchForTrouble } from "./gate";
import {
  cssEscape,
  measureSourceComposition,
  relatedSource,
  servedNeighbourhood,
  servedSourceGraph,
  sourceMapUrl,
  type SourceCompositionReport,
} from "./sourceGate";

/** The review viewport ADR 0006 and both SPECs are specified against. */
const REVIEW = { width: 2852, height: 1688 };

/**
 * How much of the field the floating chrome may cover, per tier.
 *
 * Read off `T-255`'s approved captures, which recorded them with
 * `composition.ts`'s own `coveredShare` — the same implementation this file
 * measures the build with, so the reference and the build cannot be measured by
 * two numbers that disagree. What SPEC §7 recorded:
 *
 * | Tier | Approved Explore | Approved Focus |
 * |---|---|---|
 * | `full` (2852×1688) | 3.3–4.7 % | 19.8 % |
 * | `compact` (1440×900) | 8.8 % | 4.8 % |
 * | `stack` (390×844) | — | 8.8 % |
 *
 * The bounds are the approved worst case per tier with headroom, and they are a
 * *bound* rather than a target: the production Focus spends its drawer where the
 * approved one spent a drawer plus an orbit, so a build measuring under the
 * reference is the expected direction and is not a defect.
 */
const CHROME_SHARE_BOUND: Record<"full" | "compact" | "stack", number> = {
  full: 0.25,
  compact: 0.3,
  stack: 0.35,
};

interface Scenario {
  readonly name: string;
  readonly viewport: { width: number; height: number };
  readonly colorScheme?: "dark" | "light";
  readonly locale?: "fa";
  readonly reducedMotion?: "reduce";
  /** The tier the route should report for this field. */
  readonly tier: "full" | "compact" | "stack";
  /** Whether a source is selected, which is what opens the drawer. */
  readonly focused: boolean;
  /** Whether a relationship's grounds are open under it. */
  readonly basis?: boolean;
}

/**
 * The set a reviewer is asked to look at.
 *
 * Both compositions, both themes, both directions, all three tiers, and the two
 * states that carry the most text — a brief with its grounds open, and the
 * reduced-motion capture that must look identical to the eased one.
 */
const SCENARIOS: readonly Scenario[] = [
  { name: "source-explore-dark", viewport: REVIEW, tier: "full", focused: false },
  {
    name: "source-explore-light",
    viewport: REVIEW,
    colorScheme: "light",
    tier: "full",
    focused: false,
  },
  { name: "source-explore-fa", viewport: REVIEW, locale: "fa", tier: "full", focused: false },
  { name: "source-focus-dark", viewport: REVIEW, tier: "full", focused: true, basis: true },
  {
    name: "source-focus-light",
    viewport: REVIEW,
    colorScheme: "light",
    tier: "full",
    focused: true,
    basis: true,
  },
  {
    name: "source-focus-fa",
    viewport: REVIEW,
    locale: "fa",
    tier: "full",
    focused: true,
    basis: true,
  },
  {
    name: "source-focus-reduced-motion",
    viewport: REVIEW,
    reducedMotion: "reduce",
    tier: "full",
    focused: true,
    basis: true,
  },
  { name: "source-explore-1440", viewport: { width: 1440, height: 900 }, tier: "compact", focused: false },
  {
    name: "source-focus-1440",
    viewport: { width: 1440, height: 900 },
    tier: "compact",
    focused: true,
    basis: true,
  },
  {
    name: "source-focus-1280",
    viewport: { width: 1280, height: 720 },
    tier: "compact",
    focused: true,
    basis: true,
  },
  {
    name: "source-focus-390",
    viewport: { width: 390, height: 844 },
    tier: "stack",
    focused: true,
    basis: true,
  },
];

function capturesDir(): string {
  return `${test.info().project.testDir}/../../docs/mockups/T-257/captures`;
}

async function capture(page: Page, name: string): Promise<void> {
  const file = `${capturesDir()}/${name}.png`;
  await page.screenshot({ path: file, fullPage: false });
  test.info().annotations.push({ type: "capture", description: file });
}

/** The counts this file logs beside each capture, as one line for a reviewer. */
function summarise(report: SourceCompositionReport): string {
  return JSON.stringify({
    tier: report.tier,
    direction: report.direction,
    field:
      report.field === null
        ? null
        : `${Math.round(report.field.width)}x${Math.round(report.field.height)}`,
    documentHeight: report.documentHeight,
    chrome: report.chrome.length,
    chromeShare: Number(report.chromeShare.toFixed(4)),
    collided: report.collided,
    drawer:
      report.drawer === null
        ? null
        : `${report.drawer.scrollHeight}/${report.drawer.clientHeight} ${report.drawer.overflowY}`,
  });
}

async function openScenario(
  browser: Browser,
  scenario: Scenario,
): Promise<{ page: Page; chosen: string; trouble: string[]; close: () => Promise<void> }> {
  const context = await browser.newContext({
    viewport: scenario.viewport,
    colorScheme: scenario.colorScheme ?? "dark",
    deviceScaleFactor: 1,
    ...(scenario.reducedMotion === undefined ? {} : { reducedMotion: scenario.reducedMotion }),
  });
  const page = await context.newPage();
  const { trouble } = watchForTrouble(page);
  if (scenario.locale === "fa") {
    // Set before the bundle runs, the way a returning reader has it: a locale
    // switched after layout captures a composition laid out one way and then
    // mirrored, which is a picture the application never draws.
    await page.addInitScript(() => {
      window.localStorage.setItem("x2knwldg.locale", "fa");
    });
  }

  const graph = await servedSourceGraph(page);
  // The source with relationships, so a focused capture has a drawer with
  // something in it. Which one that is is a fact about the served library.
  const chosen = relatedSource(graph);

  await page.goto(sourceMapUrl(scenario.focused ? { focus: `${chosen}:source` } : {}));
  await expect(
    page.locator('.map[data-map-of="sources"][data-map-canvas="drawing"]'),
  ).toBeVisible();
  await expect(page.locator("[data-map-stage] canvas")).toHaveCount(1);

  if (scenario.focused) {
    await expect(page.locator(`[data-source-card="${cssEscape(chosen)}"]`)).toBeVisible();
    if (scenario.basis === true) {
      await expect(page.locator("[data-source-basis]")).toBeVisible();
    }
    // The camera frames the selection and eases into place; a capture taken
    // mid-flight is a picture of a gesture rather than of a composition.
    await page.waitForTimeout(900);
  }
  return { page, chosen, trouble, close: () => context.close() };
}

test.describe("the composition, scenario by scenario", () => {
  for (const scenario of SCENARIOS) {
    test(scenario.name, async ({ browser }) => {
      const opened = await openScenario(browser, scenario);
      const { page, chosen, trouble } = opened;
      try {
        const report = await measureSourceComposition(page);
        test.info().annotations.push({ type: "composition", description: summarise(report) });
        await capture(page, scenario.name);

        // The tier is read from the route's own seam rather than inferred.
        expect(report.tier).toBe(scenario.tier);
        expect(report.direction).toBe(scenario.locale === "fa" ? "rtl" : "ltr");

        // No two floating surfaces over the same pixels. On this Map the floats
        // *are* the composition — there is no orbit — so this is the whole of
        // what "nothing overlaps" can mean here, and it is asserted rather than
        // borrowed from a measurement of cards that do not exist.
        expect(report.collided, `overlapping surfaces in ${scenario.name}`).toEqual([]);

        // The field is real: a stage with no area is a composition with nothing
        // in it, and every share below would be measured against zero.
        expect(report.field).not.toBeNull();
        expect(report.field!.width).toBeGreaterThan(0);
        expect(report.field!.height).toBeGreaterThan(0);

        expect(
          report.chromeShare,
          `chrome covers ${(report.chromeShare * 100).toFixed(1)}% of the field, more than the approved captures spend at the ${scenario.tier} tier`,
        ).toBeLessThanOrEqual(CHROME_SHARE_BOUND[scenario.tier]);

        // The workspace clause (D-153): the route is the viewport and the
        // document does not scroll. `stack` is the same deliberate exception the
        // Knowledge Map records — below 900 px the route is its own document.
        if (scenario.tier === "stack") {
          expect(report.documentHeight).toBeGreaterThanOrEqual(scenario.viewport.height);
        } else {
          expect(report.documentHeight).toBe(scenario.viewport.height);
        }

        if (!scenario.focused) {
          // Explore is the quiet overview: no drawer at all, and the picture is
          // the field rather than a reading over it.
          expect(report.drawer).toBeNull();
          await expect(page.locator("[data-source-nothing-focused]")).toBeVisible();
          expect(trouble).toEqual([]);
          return;
        }

        // Focus: one readable card, and the drawer that carries it can be read
        // to its foot however long the brief is.
        await expect(page.locator("[data-source-card]")).toHaveCount(1);
        expect(report.drawer).not.toBeNull();
        expect(report.drawer!.overflowY).toMatch(/auto|scroll/);
        if (scenario.tier === "stack") {
          // Below the `compact` minimum the route is its own document and the
          // drawer flows in it rather than sitting in a rail — the same D-153
          // exception the Knowledge Map records. So the clause is that the
          // column is reachable by scrolling the *page*, which is what a reader
          // does on a phone, rather than that it fits a viewport it never
          // claimed to fit. Measured: 2226 px of drawer in an 844 px viewport.
          expect(report.documentHeight).toBeGreaterThanOrEqual(report.drawer!.bottom);
        } else {
          expect(report.drawer!.bottom).toBeLessThanOrEqual(report.viewport.height + 1);
        }

        // Every returned relationship is a row, at every tier: the bound is on
        // what the *stage* draws, never on what the list carries.
        const served = await servedNeighbourhood(page, chosen);
        await expect(page.locator("[data-source-relations]")).toHaveAttribute(
          "data-source-relations",
          String(served.incoming.length + served.outgoing.length),
        );
        expect(trouble).toEqual([]);
      } finally {
        await opened.close();
      }
    });
  }
});

test.describe("what the approved compositions asked for, and what was built", () => {
  test("draws no orbit, and therefore no card the orbit clauses could bind to", async ({
    browser,
  }) => {
    /*
     * D-283, asserted rather than stated.
     *
     * A reviewer comparing `docs/mockups/T-255/captures/focus-*` with
     * `docs/mockups/T-257/captures/source-focus-*` will see a different picture,
     * and this test is what makes that difference a recorded decision instead of
     * a regression nobody noticed. If a later task builds the orbit, this test
     * fails — which is the correct outcome: the clause set that applies to this
     * surface would have changed, and the gate above would need the orbit
     * assertions `visual.spec.ts` already implements.
     */
    const opened = await openScenario(browser, {
      name: "orbit-check",
      viewport: REVIEW,
      tier: "full",
      focused: true,
      basis: true,
    });
    try {
      const { page } = opened;
      await expect(page.locator(".map__overlay")).toHaveCount(0);
      await expect(page.locator("[data-map-card]")).toHaveCount(0);
      await expect(page.locator("[data-orbit-pill]")).toHaveCount(0);

      // And the reading the orbit would have carried is all in the drawer, which
      // is where a reviewer should be comparing it: the card, the relationships
      // and the grounds, in one column.
      const drawer = page.locator(".map__drawer");
      await expect(drawer.locator("[data-source-card]")).toHaveCount(1);
      await expect(drawer.locator("[data-source-relations]")).toHaveCount(1);
      await expect(drawer.locator("[data-source-basis]")).toHaveCount(1);

      // The Knowledge Map's own probe, run here, reports an empty orbit: this is
      // the same instrument that measures the other Map, saying there is nothing
      // of its kind on this one.
      const { measureComposition } = await import("./composition");
      const knowledge = await measureComposition(page);
      test.info().annotations.push({
        type: "knowledge-probe",
        description: summariseKnowledge(knowledge),
      });
      expect(knowledge.cards).toEqual([]);
      expect(knowledge.pills).toEqual([]);
      expect(knowledge.orbitTier).toBeNull();
    } finally {
      await opened.close();
    }
  });
});
