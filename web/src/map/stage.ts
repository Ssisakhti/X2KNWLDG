/**
 * Which ground the Map is drawn on, and why the canvas needs to be told.
 *
 * `mapStyle.ts` used to carry one palette and say of it: "a mid-tone that is
 * legible on both is the only honest choice available here". That sentence is
 * arithmetically false, and the arithmetic is short enough to state.
 *
 * A node's or an edge's label is **text** on the canvas, so WCAG 2.2 SC 1.4.3
 * asks 4.5:1 of it at the sizes this Map draws. The two stages are `#fbfaf8`
 * (relative luminance 0.9566) and `#17161a` (0.0083). To clear 4.5:1 an ink
 * must therefore have luminance
 *
 *     <= (0.9566 + 0.05) / 4.5 - 0.05  =  0.1737   on the light stage, and
 *     >= 4.5 * (0.0083 + 0.05) - 0.05  =  0.2124   on the dark stage.
 *
 * Those two windows do not overlap. **No colour clears 4.5:1 on both**, so a
 * single palette cannot be legible on both grounds -- it can only be legible
 * on one and be measured against the other by nobody. Every one of the
 * seventeen canvas inks failed 4.5:1 on at least one stage, and four failed on
 * both.
 *
 * The marks themselves are a different question with a different answer. A
 * mark is a graphical object, so SC 1.4.11 asks 3:1, whose windows are
 * `<= 0.2855` and `>= 0.1249` -- these *do* overlap, which is why one mid-tone
 * table was a defensible choice for the shapes even though it was never one
 * for the words beside them.
 *
 * So the stage is read here and the ink table is chosen by it. This is the
 * same shape as `motion.ts`, and for the same reasons:
 *
 * **Read at the call, not at module load.** A value captured when the bundle
 * evaluated would answer for the whole session, and the preference changes --
 * a system setting at sunset, a devtools override, a laptop lid closed on an
 * external display. The reducers run on every refresh, so reading here costs
 * one `matchMedia` lookup per refresh and is always current.
 *
 * **`light` for an environment that cannot answer.** No `window`, no
 * `matchMedia`, or a `matchMedia` that throws on an unknown feature. An
 * unanswerable query is not a preference; jsdom is such an environment, which
 * is why the unit tests read the light table without stubbing anything.
 */

/** The two grounds the Map is ever drawn on. They are the two `--bg` values. */
export type MapStage = "light" | "dark";

/** The stage this environment asks for. `light` when it cannot be asked. */
export function mapStage(): MapStage {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return "light";
  try {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  } catch {
    return "light";
  }
}

/**
 * Call *listener* whenever the stage changes, and return the unsubscribe.
 *
 * The canvas is not the DOM: a CSS custom property re-resolves itself when the
 * media query flips and a colour already handed to WebGL does not. Without
 * this, switching the system theme with the Map open leaves the previous
 * stage's inks painted on the new ground -- which is the failing state this
 * module exists to remove, reached from the other direction.
 *
 * A no-op unsubscribe for an environment that cannot answer, so a caller's
 * cleanup path needs no branch of its own.
 */
export function onMapStageChange(listener: (stage: MapStage) => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return () => {};
  let query: MediaQueryList;
  try {
    query = window.matchMedia("(prefers-color-scheme: dark)");
  } catch {
    return () => {};
  }
  const handle = (event: MediaQueryListEvent) => listener(event.matches ? "dark" : "light");
  // `addEventListener` on a `MediaQueryList` is the current API; Safari carried
  // only `addListener` until 14. Neither is assumed to be present.
  if (typeof query.addEventListener === "function") {
    query.addEventListener("change", handle);
    return () => query.removeEventListener("change", handle);
  }
  if (typeof query.addListener === "function") {
    query.addListener(handle);
    return () => query.removeListener(handle);
  }
  return () => {};
}
