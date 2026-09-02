/**
 * Test setup.
 *
 * Testing Library registers its own cleanup only when a runner exposes global
 * hooks. This project imports `describe`/`it`/`expect` explicitly, so the
 * cleanup is registered here instead -- without it a component from one test
 * is still mounted during the next, and a query that should find one element
 * finds three.
 */

import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  // `HashRouter` navigates by mutating the location, and jsdom keeps one
  // location for the whole file: without this, a test that opened a reader
  // leaves the next test's `App` mounted on that route.
  window.location.hash = "";
  document.documentElement.removeAttribute("dir");
  document.documentElement.removeAttribute("lang");
  try {
    window.localStorage.clear();
  } catch {
    // Some environments do not expose storage; the provider tolerates that too.
  }
});
