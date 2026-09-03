/**
 * D-203 — Units mode made N sequential requests and re-ran them per keystroke.
 *
 * The fan-out was `for (const source of sources) groups.push(await
 * loadGroup(...))`: fifty strictly serial round trips with nothing rendered
 * until the last landed. And the confidence filter is an unthrottled
 * `onChange` on a number input, so every keypress restarted all fifty.
 */

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Source } from "../api/contract";
import { I18nProvider } from "../i18n";
import { UnitsBrowser } from "./UnitsBrowser";

const SOURCES: Source[] = Array.from({ length: 12 }, (_, index) => ({
  schema_version: "1.0",
  id: `youtube:v${index}`,
  source_type: "youtube",
  external_id: `v${index}`,
  url: null,
  title: `Video ${index}`,
  canonical_dir: `output/v${index}`,
  adapter: { name: "youtube", version: "1.0" },
  status: { validation: "PASS", coverage: "PASS", overall: "PASS" },
  artifact_ids: [],
})) as unknown as Source[];

/** A fetch that reports concurrency: how many were in flight at the peak. */
function watchingFetch() {
  let live = 0;
  let peak = 0;
  const settle: (() => void)[] = [];
  const calls: string[] = [];
  const load = vi.fn(async (input: RequestInfo | URL) => {
    calls.push(String(input));
    live += 1;
    peak = Math.max(peak, live);
    await new Promise<void>((resolve) => settle.push(resolve));
    live -= 1;
    return new Response(
      JSON.stringify({
        api_version: "v1",
        schema_version: "1.0",
        data: [],
        page: { limit: 50, next_cursor: null, total: 0 },
      }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  });
  return {
    load,
    calls,
    peak: () => peak,
    release: () => {
      const pending = settle.splice(0, settle.length);
      for (const resolve of pending) resolve();
    },
  };
}

beforeEach(() => vi.useRealTimers());
afterEach(() => vi.unstubAllGlobals());

describe("Units mode", () => {
  it("asks several sources at once rather than one after another", async () => {
    const fetching = watchingFetch();
    vi.stubGlobal("fetch", fetching.load);

    render(
      <I18nProvider>
        <UnitsBrowser
          sources={SOURCES}
          filters={{ kind: "", provenance: "", minConfidence: "" }}
        />
      </I18nProvider>,
    );

    // More than one request is in flight before any of them has answered,
    // which is the whole difference from the serial walk.
    await waitFor(() => expect(fetching.peak()).toBeGreaterThan(1));
    // And bounded: fifty at once is a thundering herd at a local server.
    expect(fetching.peak()).toBeLessThanOrEqual(6);

    // Drain until the fan-out finishes.
    for (let round = 0; round < SOURCES.length + 2; round += 1) {
      fetching.release();
      await Promise.resolve();
    }
    await waitFor(() => expect(fetching.calls.length).toBe(SOURCES.length));
  });

  it("does not restart the fan-out on every keystroke", async () => {
    const fetching = watchingFetch();
    vi.stubGlobal("fetch", fetching.load);

    const { rerender } = render(
      <I18nProvider>
        <UnitsBrowser
          sources={SOURCES.slice(0, 2)}
          filters={{ kind: "", provenance: "", minConfidence: "" }}
        />
      </I18nProvider>,
    );
    await waitFor(() => expect(fetching.calls.length).toBe(2));
    const afterFirstPass = fetching.calls.length;

    // "0.85", typed.
    for (const value of ["0", "0.", "0.8", "0.85"]) {
      rerender(
        <I18nProvider>
          <UnitsBrowser
            sources={SOURCES.slice(0, 2)}
            filters={{ kind: "", provenance: "", minConfidence: value }}
          />
        </I18nProvider>,
      );
    }

    // Nothing yet: the filter has not held still.
    expect(fetching.calls.length).toBe(afterFirstPass);

    // One pass once it settles, for the value that was actually typed.
    await waitFor(() => expect(fetching.calls.length).toBe(afterFirstPass + 2), {
      timeout: 2000,
    });
    expect(fetching.calls.every((url) => !url.includes("min_confidence=0.8&"))).toBe(true);
    expect(fetching.calls.slice(-2).every((url) => url.includes("min_confidence=0.85"))).toBe(
      true,
    );
  });

  it("announces that it is loading rather than only showing it", async () => {
    const fetching = watchingFetch();
    vi.stubGlobal("fetch", fetching.load);
    render(
      <I18nProvider>
        <UnitsBrowser
          sources={SOURCES.slice(0, 1)}
          filters={{ kind: "", provenance: "", minConfidence: "" }}
        />
      </I18nProvider>,
    );
    expect(screen.getByRole("status")).toBeTruthy();
  });
});
