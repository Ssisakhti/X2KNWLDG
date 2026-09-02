/**
 * The Map's motion policy (`T-208`).
 *
 * Two surfaces animate on this route and neither of them is CSS. The
 * stylesheet's `prefers-reduced-motion` block covers everything the browser
 * animates; a camera driven from JavaScript is invisible to it, and the
 * Map's zoom and reset controls are exactly that -- Sigma's camera eases
 * between two states over a duration of its own choosing, on a canvas the
 * media query cannot reach.
 *
 * So the query is read here, once, and the answer is turned into the camera's
 * own argument. A reader who has asked their system for less motion gets the
 * new view immediately rather than a quarter-second glide.
 *
 * **`undefined` rather than a number of our own.** When motion is welcome
 * this returns nothing at all, which leaves the renderer's default duration
 * in place. Inventing a number here would be a fourth Map constant chosen by
 * argument and measured by nobody, and it would silently override whatever the
 * renderer decides is right for its own gesture. `T-209` measured what the
 * renderer does with each answer, in frames on a real canvas: an eased zoom is
 * still mid-flight at 142 ms and final by 230, while `{ duration: 0 }` is
 * final on the first frame after the press.
 *
 * **Read at the call, not at module load.** The preference can change while
 * the page is open -- a system setting, or a browser devtools override -- and
 * a value captured when the bundle evaluated would answer for the session.
 * There is no subscription for the same reason there is no state: the answer
 * is needed only at the moment a control is pressed.
 */

/** What a camera gesture may be told about its own duration. */
export interface MapCameraAnimation {
  /** Milliseconds. `0` is "arrive now", which is what reduced motion asks for. */
  duration: number;
}

/**
 * Whether this environment asks for reduced motion.
 *
 * `false` for an environment that cannot answer: no `window`, no
 * `matchMedia`, or a `matchMedia` that throws on an unknown feature. An
 * unanswerable query is not a preference, and treating it as one would strip
 * the motion from every browser too old to be asked.
 */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
  try {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  } catch {
    return false;
  }
}

/**
 * The animation argument for a camera gesture, or `undefined` to keep the
 * renderer's own default.
 */
export function cameraAnimation(): MapCameraAnimation | undefined {
  return prefersReducedMotion() ? { duration: 0 } : undefined;
}
