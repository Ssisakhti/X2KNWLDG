/**
 * D-203 — the one paged-list ladder, and the three defects the five copies had.
 *
 * 1. A failed *later* page destroyed the pages already loaded, because
 *    `usePaged.loadMore` set the same `error` a failed first page sets and
 *    every call site branched on that field before rendering items.
 * 2. "More" dropped keyboard focus on two of the five, which `withFocusRescue`
 *    fixes and D-180 had already fixed for seven other controls.
 * 3. Async status was announced nowhere: every loading state was a bare
 *    `<p class="muted">`.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it } from "vitest";

import { ApiFailure } from "../api/errors";
import type { PagedState } from "../api/usePaged";
import { I18nProvider } from "../i18n";
import { PagedList } from "./PagedList";

function state(overrides: Partial<PagedState<string>> = {}): PagedState<string> {
  return {
    items: [],
    total: null,
    hasMore: false,
    status: "ready",
    loadingMore: false,
    error: null,
    moreError: null,
    loadMore: () => {},
    reload: () => {},
    ...overrides,
  };
}

function show(value: PagedState<string>) {
  return render(
    <I18nProvider>
      <div data-focus-anchor>
        <PagedList state={value} label="sources" empty="nothing here">
          {(items) => items.map((item) => <p key={item}>{item}</p>)}
        </PagedList>
      </div>
    </I18nProvider>,
  );
}

describe("PagedList", () => {
  it("keeps the loaded items when a later page fails", () => {
    show(
      state({
        items: ["A1", "A2"],
        total: 50,
        hasMore: true,
        moreError: new ApiFailure("internal", "the server said no"),
      }),
    );

    // Everything already loaded is still on screen.
    expect(screen.getByText("A1")).toBeTruthy();
    expect(screen.getByText("A2")).toBeTruthy();
    // The gap is reported where it is.
    expect(screen.getByText(/the server said no/)).toBeTruthy();
    // And the button is still there to try the same page again.
    expect(screen.getByRole("button", { name: /more/i })).toBeTruthy();
  });

  it("replaces the list only when the first page failed", () => {
    show(state({ error: new ApiFailure("internal", "nothing arrived") }));
    expect(screen.getByText(/nothing arrived/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /more/i })).toBeNull();
  });

  it("announces which list is loading, and what arrived", () => {
    const { unmount } = show(state({ status: "loading" }));
    const loading = screen.getByRole("status");
    expect(loading.textContent).toContain("sources");
    expect(loading.dataset.pagedStatus).toBe("loading");
    unmount();

    show(state({ items: ["A1"], total: 1 }));
    expect(screen.getByRole("status").textContent).toContain("1");
  });

  it("says the walk found nothing rather than saying nothing", () => {
    show(state({ items: [], total: 0 }));
    expect(screen.getByRole("status").textContent).toContain("nothing here");
  });

  it("keeps focus in the page when More unmounts itself", async () => {
    // The last page arrives, `hasMore` goes false, the button unmounts. Two of
    // the five call sites built this button unwrapped.
    function Walk() {
      const [done, setDone] = useState(false);
      return (
        <I18nProvider>
          <div data-focus-anchor data-testid="region">
            <PagedList
              state={state({
                items: ["A1"],
                hasMore: !done,
                loadMore: () => setDone(true),
              })}
              label="sources"
              empty="nothing here"
            >
              {(items) => items.map((item) => <p key={item}>{item}</p>)}
            </PagedList>
          </div>
        </I18nProvider>
      );
    }

    render(<Walk />);
    const button = screen.getByRole("button", { name: /more/i });
    button.focus();
    expect(document.activeElement).toBe(button);

    fireEvent.click(button);
    await waitFor(() => expect(screen.queryByRole("button", { name: /more/i })).toBeNull());
    await waitFor(() => expect(document.activeElement).toBe(screen.getByTestId("region")));
  });
});
