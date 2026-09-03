/**
 * What the composition *is*, measured off the running build (`T-215`).
 *
 * `T-213` wrote these checks as a standalone script, `scripts/measure_orbit.ts`,
 * and `PROJECT_MANAGEMENT.md` §11 states what `T-215` does with them: the gate's
 * geometry assertions are that script's checks **moved into the browser suite**
 * and run per scenario, not a second implementation of them. So the measuring
 * lives here, once, and both callers read the same numbers off the same probe:
 *
 * - `browser/visual.spec.ts` asserts on them, per scenario;
 * - `scripts/measure_orbit.ts` prints them, which is how the numbers in
 *   `SPEC.md` §14 and D-193 were produced and how they stay re-checkable
 *   against a live build.
 *
 * Nothing here asserts and nothing here waits. A measurement that decided when
 * the picture was ready would be a second settling policy beside `settledStage`,
 * and two settling policies are one more than a composition can have: the whole
 * point of "placed plus counted equals returned" is that both numbers come from
 * *one* settled placement.
 *
 * **No named function inside the page callback, deliberately.** `tsx` compiles
 * this file with esbuild's `keepNames` for the script caller, which wraps every
 * function bound to a name -- a declaration, or an arrow assigned to a `const`
 * -- in a `__name` call that exists in the module and not in the page. The
 * evaluation then dies with a `ReferenceError` that says nothing about
 * geometry. `T-213` found that the hard way; the comment it left in
 * `measure_orbit.ts` is the reason the rectangle-overlap test below is written
 * out at each of its two use sites rather than extracted. It is the one place
 * in this program where duplication is deliberate.
 */

import type { Page } from "@playwright/test";

/** A rectangle in viewport pixels, which is the only space these compare in. */
export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
  width: number;
  height: number;
}

/** One card the orbit placed, and what the route says it is to the focus. */
export interface CardMark {
  id: string;
  primary: boolean;
  /** `incoming`, `outgoing`, or `centre` for the focused card itself. */
  side: string;
  hops: number;
  rect: Rect;
}

/** One relation's horizontal text pill, and whether it found a clear seat. */
export interface PillMark {
  key: string;
  /**
   * Every seat was taken and the pill was kept on its path anyway.
   *
   * `OrbitPill.crowded`, which the route publishes as
   * `data-orbit-pill-crowded` precisely so a gate can refuse the picture
   * rather than let a label sit on a card unremarked.
   */
  crowded: boolean;
  /** The pill's text is horizontal: no rotation, no vertical writing mode. */
  horizontal: boolean;
  rect: Rect;
}

/** One floating control the cards have to stay out from under. */
export interface ChromeMark {
  name: string;
  rect: Rect;
}

/** Everything one scenario's composition can be asked about at one moment. */
export interface CompositionReport {
  /** Which of SPEC §5's three compositions the measured field can hold. */
  tier: string | null;
  /** The tier the overlay itself laid out with; `null` when there is no orbit. */
  orbitTier: string | null;
  /** The document's own direction, which is what mirrors the two sides. */
  direction: string;
  /** The field: the stage's box, which in the workspace is the usable route. */
  field: Rect | null;
  viewport: { width: number; height: number };
  /** The document's height, which D-153 requires to be the viewport's. */
  documentHeight: number;
  /** Neighbours the server returned, as the related list counted them. */
  returned: number;
  /** The depth that answer was asked at, so a caller can re-ask the same one. */
  depth: number;
  /** The focused card's identity, or `null` with nothing selected. */
  centre: string | null;
  /** Neighbour cards on the field: the primary is not one of them. */
  placed: number;
  /** Neighbours counted instead of carded, as the route totals them. */
  omittedTotal: number;
  /** Those counts by their stated reason (`no_room`, `budget`, ...). */
  omissions: Record<string, number>;
  cards: CardMark[];
  pills: PillMark[];
  chrome: ChromeMark[];
  /** Marks outside the field: ADR 0006's "no card is clipped". */
  clipped: string[];
  /** Mark over mark: "no two cards overlap", and no pill over either. */
  collided: string[];
  /** Marks under a floating control, which is the same failure one surface up. */
  covered: string[];
  /** Pills that were seated with no clear run: a label over something. */
  crowded: string[];
  /** Pills whose text is not horizontal, which ADR 0006 clause 5 forbids. */
  rotated: string[];
}

/**
 * Measure the composition on screen, once.
 *
 * The stage's box is the field, every mark is measured in viewport pixels, and
 * the three violation lists are *lists* rather than counts so a failure names
 * the card it is about instead of reporting a number that went up.
 */
export async function measureComposition(page: Page): Promise<CompositionReport> {
  return page.evaluate(() => {
    const route = document.querySelector(".map");
    const stage = document.querySelector("[data-map-stage]");
    const overlay = document.querySelector(".map__overlay");
    const box = stage === null ? null : stage.getBoundingClientRect();
    const field =
      box === null
        ? null
        : {
            left: box.left,
            top: box.top,
            right: box.right,
            bottom: box.bottom,
            width: box.width,
            height: box.height,
          };

    const cardNodes = [...document.querySelectorAll(".map__overlay [data-map-card]")];
    const pillNodes = [...document.querySelectorAll("[data-orbit-pill]")];
    const chromeNodes = [...document.querySelectorAll("[data-map-chrome]")];

    const cards = cardNodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return {
        id: node.getAttribute("data-map-card") ?? "?",
        primary: node.getAttribute("data-map-card-primary") === "true",
        side: node.getAttribute("data-map-card-side") ?? "centre",
        hops: Number(node.getAttribute("data-map-card-hops") ?? 0),
        rect: {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        },
      };
    });

    const pills = pillNodes.map((node) => {
      const rect = node.getBoundingClientRect();
      const style = getComputedStyle(node);
      // A rotation or a skew shows up as a non-zero `b` or `c` in the 2D
      // matrix; `none` is the untransformed case and is what a horizontal
      // pill is expected to report. The writing mode is the other way text
      // turns on its side without any transform at all.
      const matrix = style.transform.startsWith("matrix(")
        ? style.transform.slice(7, -1).split(",").map(Number)
        : [1, 0, 0, 1, 0, 0];
      return {
        key: node.getAttribute("data-orbit-pill") ?? "?",
        crowded: node.getAttribute("data-orbit-pill-crowded") === "true",
        horizontal:
          Math.abs(matrix[1] ?? 0) < 0.001 &&
          Math.abs(matrix[2] ?? 0) < 0.001 &&
          style.writingMode.startsWith("horizontal"),
        rect: {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        },
      };
    });

    const chrome = chromeNodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return {
        name: node.className,
        rect: {
          left: rect.left,
          top: rect.top,
          right: rect.right,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        },
      };
    });

    const marks = [...cards, ...pills.map((pill) => ({ id: pill.key, rect: pill.rect }))];
    const clipped: string[] = [];
    const collided: string[] = [];
    const covered: string[] = [];
    if (field !== null) {
      for (const mark of marks) {
        if (
          mark.rect.left < field.left - 0.5 ||
          mark.rect.top < field.top - 0.5 ||
          mark.rect.right > field.right + 0.5 ||
          mark.rect.bottom > field.bottom + 0.5
        ) {
          clipped.push(mark.id);
        }
        for (const control of chrome) {
          if (
            control.rect.width > 0 &&
            control.rect.height > 0 &&
            mark.rect.left < control.rect.right &&
            control.rect.left < mark.rect.right &&
            mark.rect.top < control.rect.bottom &&
            control.rect.top < mark.rect.bottom
          ) {
            covered.push(`${mark.id} under ${control.name}`);
          }
        }
      }
      for (let i = 0; i < marks.length; i += 1) {
        for (let j = i + 1; j < marks.length; j += 1) {
          const one = marks[i];
          const two = marks[j];
          if (one === undefined || two === undefined) continue;
          if (
            one.rect.left < two.rect.right &&
            two.rect.left < one.rect.right &&
            one.rect.top < two.rect.bottom &&
            two.rect.top < one.rect.bottom
          ) {
            collided.push(`${one.id} / ${two.id}`);
          }
        }
      }
    }

    const omissions: Record<string, number> = {};
    for (const node of document.querySelectorAll("[data-map-stage-omission]")) {
      const reason = node.getAttribute("data-map-stage-omission") ?? "?";
      omissions[reason] = Number((node.textContent ?? "").trim().split(/\s+/u)[0] ?? 0);
    }

    const related = document.querySelector("[data-map-related]");
    return {
      tier: route === null ? null : route.getAttribute("data-map-tier"),
      orbitTier: overlay === null ? null : overlay.getAttribute("data-map-orbit-tier"),
      direction: document.documentElement.getAttribute("dir") ?? "ltr",
      field,
      viewport: { width: window.innerWidth, height: window.innerHeight },
      documentHeight: document.documentElement.scrollHeight,
      returned: Number(related?.getAttribute("data-map-related") ?? 0),
      depth: Number(related?.getAttribute("data-map-related-depth") ?? 1),
      centre: cards.find((card) => card.primary)?.id ?? null,
      placed: cards.filter((card) => !card.primary).length,
      omittedTotal: Number(
        document.querySelector("[data-map-stage-omitted]")?.getAttribute("data-map-stage-omitted") ??
          0,
      ),
      omissions,
      cards,
      pills,
      chrome,
      clipped,
      collided,
      covered,
      crowded: pills.filter((pill) => pill.crowded).map((pill) => pill.key),
      rotated: pills.filter((pill) => !pill.horizontal).map((pill) => pill.key),
    };
  });
}

/** The three counts `SPEC.md` §14's table quotes, as one line for a log. */
export function summarise(report: CompositionReport): string {
  return JSON.stringify({
    tier: report.tier,
    field: report.field === null ? null : `${Math.round(report.field.width)}x${Math.round(report.field.height)}`,
    documentHeight: report.documentHeight,
    returned: report.returned,
    placed: report.placed,
    omittedTotal: report.omittedTotal,
    omissions: report.omissions,
    pills: report.pills.length,
    clipped: report.clipped,
    collided: report.collided,
    covered: report.covered,
    crowded: report.crowded,
    rotated: report.rotated,
    accounted: report.placed + report.omittedTotal === report.returned,
  });
}
