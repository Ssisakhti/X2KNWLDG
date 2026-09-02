/**
 * D-179: there was no error boundary anywhere in `web/src`.
 *
 * React's behaviour without one is to unmount the whole tree, so any uncaught
 * render error gave the reader a blank document with no retry and no statement
 * of what happened. ADR 0005 names "an error throw" as a path invariant 10 must
 * survive — one renderer created, one alive, none leaked — and a root that
 * unmounts leaves nothing to observe that the cleanup ran.
 */

import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { I18nProvider } from "../i18n";

import { RouteErrorBoundary } from "./RouteErrorBoundary";

function Throwing({ throwNow }: { throwNow: boolean }) {
  if (throwNow) throw new Error("the view could not be drawn");
  return <p>the view</p>;
}

function Harness({ throwNow }: { throwNow: boolean }) {
  const [attempt, setAttempt] = useState(0);
  return (
    <I18nProvider initialLocale="en">
      <p>the shell</p>
      <RouteErrorBoundary resetKey={attempt} onRetry={() => setAttempt((n) => n + 1)}>
        <Throwing key={attempt} throwNow={throwNow && attempt === 0} />
      </RouteErrorBoundary>
    </I18nProvider>
  );
}

beforeEach(() => {
  // React logs the caught error itself, and `componentDidCatch` logs the stack
  // on purpose (this project sends nothing anywhere). Neither is the test's.
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("a view that throws", () => {
  it("is replaced by a statement rather than taking the page down", () => {
    render(<Harness throwNow />);
    const caught = document.querySelector("[data-error-boundary='caught']");
    expect(caught).not.toBeNull();
    expect(caught?.getAttribute("role")).toBe("alert");
    // The server's own words are shown, never instead of the explanation.
    expect(caught?.textContent).toContain("the view could not be drawn");
    // And the shell around it survived, so the reader is one click from
    // somewhere that works.
    expect(screen.getByText("the shell")).not.toBeNull();
  });

  it("offers a retry that remounts the view rather than resuming it", () => {
    render(<Harness throwNow />);
    fireEvent.click(screen.getByText("Try this view again"));
    expect(screen.getByText("the view")).not.toBeNull();
    expect(document.querySelector("[data-error-boundary='caught']")).toBeNull();
  });

  it("stays out of the way when nothing throws", () => {
    render(<Harness throwNow={false} />);
    expect(screen.getByText("the view")).not.toBeNull();
    expect(document.querySelector("[data-error-boundary]")).toBeNull();
  });
});
