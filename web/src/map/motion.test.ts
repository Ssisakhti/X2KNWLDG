/**
 * `T-208`: a camera the stylesheet cannot reach still answers the
 * reduced-motion preference.
 *
 * The stylesheet's own `@media (prefers-reduced-motion: reduce)` block covers
 * everything the browser animates, and it covers nothing the Map animates:
 * zoom, zoom out and reset are eased by Sigma's camera, in JavaScript, on a
 * canvas. So the query is read here, and these tests are about the two
 * answers and the two non-answers.
 */

import { afterEach, describe, expect, it, vi } from "vitest";

import { cameraAnimation, prefersReducedMotion } from "./motion";

/** A `matchMedia` that answers *matches* for the reduced-motion query only. */
function stubMatchMedia(matches: boolean): void {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: query.includes("prefers-reduced-motion") ? matches : false,
    media: query,
  }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the Map's motion policy", () => {
  it("reads the preference and asks the camera to arrive immediately", () => {
    stubMatchMedia(true);
    expect(prefersReducedMotion()).toBe(true);
    expect(cameraAnimation()).toEqual({ duration: 0 });
  });

  it("keeps the renderer's own duration when motion is welcome", () => {
    stubMatchMedia(false);
    expect(prefersReducedMotion()).toBe(false);
    // Not `{ duration: 250 }`: a number invented here would override whatever
    // the renderer thinks is right for its own gesture, and would be a fourth
    // Map constant nobody has measured.
    expect(cameraAnimation()).toBeUndefined();
  });

  it("treats an environment that cannot be asked as no preference", () => {
    vi.stubGlobal("matchMedia", undefined);
    expect(prefersReducedMotion()).toBe(false);
    expect(cameraAnimation()).toBeUndefined();
  });

  it("treats a `matchMedia` that throws as no preference, not as a refusal", () => {
    vi.stubGlobal("matchMedia", () => {
      throw new Error("unknown media feature");
    });
    expect(prefersReducedMotion()).toBe(false);
  });

  it("reads the preference at the call, so it can change while the page is open", () => {
    stubMatchMedia(false);
    expect(cameraAnimation()).toBeUndefined();
    stubMatchMedia(true);
    expect(cameraAnimation()).toEqual({ duration: 0 });
  });
});
