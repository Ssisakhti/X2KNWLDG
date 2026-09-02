/**
 * What the Map is allowed to say about itself (`T-208`, D-129).
 *
 * Five states were already rendered on this route and each was decided at its
 * own site: a loading line, an empty note inside the counts, a partial extent,
 * an `ApiFailure` panel and a renderer refusal. Written that way they are five
 * independent conditions, and the ones that matter are the *pairs they must
 * not collapse into*:
 *
 * - **Empty is not absent.** A page that arrived and named no node is a
 *   statement about the library. No page having arrived is a statement about
 *   the request. Rendering "this Map holds nothing" for the second is a claim
 *   the client cannot make, and it is the shape of D-068 -- an empty answer
 *   from a question nobody asked, presented as an answer.
 * - **Partial is not whole.** `complete` is `GraphSnapshot`'s own conclusion
 *   over the cursor, the held edges and the API's `truncated` (D-123). It is
 *   read, never recomputed here, and never inferred from a page's length.
 * - **Refused is not empty.** A server that refused the question drew nothing
 *   and counted nothing; so did a library with no entities. The first has an
 *   error to state and a retry to offer.
 * - **Undrawn is not absent.** A browser with no WebGL2 has the whole graph
 *   loaded and no picture of it. The counts, the outline and every list stay
 *   true, and the missing picture is its own stated state (D-129).
 *
 * This module is those distinctions as two total functions over what the walk
 * and the renderer already report, so the view renders one message per state
 * and a test can assert the pairs directly rather than through the DOM. It
 * holds no message text: the catalogue key is chosen at the use site, because
 * a computed key defeats the guard that tells a shipped string from an
 * abandoned one (§8.6).
 *
 * It is not a store and not a second snapshot. Every number it reports is
 * copied out of `GraphSnapshotState`.
 */

import { ApiFailure } from "../api/errors";
import { GraphConflictError } from "./graphProjection";
import type { GraphWalkState } from "./graphWalk";

/**
 * What the accumulated graph is, in one word.
 *
 * `unasked` is the state before any page: `idle`, or a walk whose first
 * request was cancelled. It is deliberately *not* `empty`.
 */
export type GraphReadingKind =
  | "unasked"
  | "loading"
  | "refused"
  | "conflict"
  | "empty"
  | "partial"
  | "whole";

export interface GraphReading {
  kind: GraphReadingKind;
  /** Nodes drawn, as the snapshot counted them. `0` before any page. */
  nodes: number;
  /** Nodes the server counted for this question; `null` is "did not count". */
  knownNodeTotal: number | null;
  /** Whether a continuation page exists, from `next_cursor`. */
  hasMore: boolean;
  /** Whether *this* reading is one the counts panel can describe. */
  counted: boolean;
}

/**
 * The graph's state, from the walk's own report.
 *
 * The order of the clauses is the order of the claims. An error outranks a
 * count, because a snapshot that kept its previous pages and then failed must
 * not report those pages as the answer to the question that failed; a
 * conflict outranks a generic failure, because a refused *page* is a defect
 * in the data rather than in the request (D-125). `loadingMore` is
 * deliberately not consulted: a continuation in flight over a drawn graph is
 * still that drawn graph, and it is reported beside the "load more" control
 * instead.
 */
export function describeGraph(state: GraphWalkState): GraphReading {
  const snapshot = state.snapshot;
  const nodes = snapshot?.nodes ?? 0;
  const knownNodeTotal = snapshot?.knownNodeTotal ?? null;
  const hasMore = snapshot?.hasMore ?? false;
  const pages = snapshot?.pagesApplied ?? 0;
  const base = { nodes, knownNodeTotal, hasMore };

  if (state.error instanceof GraphConflictError) {
    return { ...base, kind: "conflict", counted: pages > 0 };
  }
  if (state.error instanceof ApiFailure) {
    return { ...base, kind: "refused", counted: pages > 0 };
  }
  if (state.status === "loading") return { ...base, kind: "loading", counted: pages > 0 };
  if (pages === 0) return { ...base, kind: "unasked", counted: false };
  if (nodes === 0) return { ...base, kind: "empty", counted: true };
  // `complete` is the snapshot's conclusion, not a comparison done here.
  return { ...base, kind: snapshot?.complete === true ? "whole" : "partial", counted: true };
}

/**
 * Why the renderer is not drawing, when it is not.
 *
 * The two phases are two different failures and were one message until
 * `T-208` separated them. `module` is the dynamic `import` refusing -- a
 * browser with no WebGL2 never gets a renderer to construct, and no control
 * on this route will ever work. `create` is a renderer that was reached and
 * refused this container, which is almost always its size
 * (`allowInvalidContainer: false`, D-129) and often recovers on the next
 * layout. Telling a reader to try a different browser when the stage merely
 * has no height sends them somewhere plausible and wrong.
 */
export interface RendererFault {
  phase: "module" | "create";
  /** The failure's own message, shown verbatim and never translated. */
  detail: string;
}

export type CanvasReadingKind = "drawing" | "pending" | "nothing" | "unavailable" | "refused";

export interface CanvasReading {
  kind: CanvasReadingKind;
  /** The fault's own text, when there is a fault. */
  detail: string | null;
  /** Whether there is a live camera for the zoom and reset controls to drive. */
  interactive: boolean;
}

/**
 * The canvas's state.
 *
 * A fault outranks everything, because a fault is why there is no picture. A
 * graph with no node is `nothing` rather than `drawing`: there is a renderer,
 * and it is drawing an empty stage, which is a picture of nothing and must
 * not read as a picture that failed either.
 */
export function describeCanvas(input: {
  fault: RendererFault | null;
  /**
   * Whether a live renderer is holding the graph *now*.
   *
   * Not "a factory arrived and a page exists". React runs a render and then
   * its effects, so the render that first sees a page precedes the effect
   * that hands the graph to the renderer -- and a canvas described as drawing
   * during that render is describing something that has not happened yet.
   * `T-207` found the same off-by-one-render in the constellation's first
   * placement; here it made the Map claim a picture for one render before
   * losing it again, which flipped the companion panel's step twice.
   */
  holding: boolean;
  nodes: number;
}): CanvasReading {
  if (input.fault !== null) {
    return {
      kind: input.fault.phase === "module" ? "unavailable" : "refused",
      detail: input.fault.detail,
      interactive: false,
    };
  }
  if (!input.holding) return { kind: "pending", detail: null, interactive: false };
  if (input.nodes === 0) return { kind: "nothing", detail: null, interactive: true };
  return { kind: "drawing", detail: null, interactive: true };
}
