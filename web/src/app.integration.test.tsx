/**
 * The whole application against the real server.
 *
 * The unit tests stub `fetch` and prove the components behave; this one proves
 * the wiring -- routes, client, envelopes, the byte channel -- against
 * `create_app(project_root=...)` over the committed run fixtures. It is the
 * check that a mock cannot give: every payload here is one the server actually
 * produced.
 *
 * Skipped unless `X2KNWLDG_API_BASE` names a running server:
 *
 *     npm run dev:api
 *     X2KNWLDG_API_BASE=http://127.0.0.1:8931 npm test
 *
 * The only thing stubbed is the *origin*. The application asks for `/api/...`
 * on its own origin, which is what the Vite proxy and the production server
 * both provide; jsdom has no such origin, so relative API paths are resolved
 * against the base under test and nothing else is touched.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

declare const process: { env: Record<string, string | undefined> };

const BASE = process.env.X2KNWLDG_API_BASE;

describe.skipIf(BASE === undefined || BASE === "")("the application, end to end", () => {
  beforeEach(() => {
    const real = globalThis.fetch;
    vi.stubGlobal("fetch", ((input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === "string" ? input : input.toString();
      return real(url.startsWith("/api") ? `${BASE}${url}` : url, init);
    }) as typeof fetch);
  });

  afterEach(() => vi.unstubAllGlobals());

  it("lists the fixture sources with their real statuses", async () => {
    render(<App />);
    await waitFor(
      () => expect(document.querySelectorAll("[data-source-id]").length).toBeGreaterThan(0),
      { timeout: 5000 },
    );
    const statuses = [...document.querySelectorAll("[data-source-id] [data-status]")].map((node) =>
      node.getAttribute("data-status"),
    );
    expect(statuses).toContain("PASS");
    expect(statuses).toContain("PARTIAL");
    expect(statuses).toContain("FAIL");
  });

  it("opens a source in the reader and reads its transcript from the byte channel", async () => {
    /*
     * The source is chosen by *medium*, and the count is a floor rather than an
     * equality.
     *
     * Both used to be facts about a library of three YouTube runs: exactly three
     * cards, and the first one has a transcript. D-281 put a Twitter run in the
     * served corpus, so the count is four and the first card is an X post —
     * which has no transcript, because that medium has none. This test is about
     * the Reader reading captions through the byte channel, so it opens a
     * YouTube source and leaves the library's size to the test above, which is
     * the one whose subject that is.
     */
    render(<App />);
    await waitFor(
      () => expect(document.querySelectorAll("[data-source-id]").length).toBeGreaterThanOrEqual(3),
      { timeout: 5000 },
    );

    const card = [...document.querySelectorAll("[data-source-id]")].find((node) =>
      (node.getAttribute("data-source-id") ?? "").startsWith("youtube:"),
    );
    expect(card, "the served library holds no YouTube source").toBeDefined();
    const link = card!.querySelector("a") as HTMLAnchorElement;
    fireEvent.click(link, { button: 0 });

    await waitFor(() => expect(screen.getByText("Canonical directory")).not.toBeNull(), {
      timeout: 5000,
    });

    fireEvent.click(screen.getByText("Transcript"));
    await waitFor(() => expect(document.querySelectorAll(".caption-row").length).toBeGreaterThan(0), {
      timeout: 5000,
    });

    // No local media exists for a YouTube source, and the embed is not loaded
    // until asked: nothing has been requested from the embed host.
    expect(screen.getByText(/No local media file is indexed/)).not.toBeNull();
    expect(document.querySelector("iframe")).toBeNull();
  });

  it("searches over the real index and marks a caption hit unaddressable", async () => {
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("Search")).not.toBeNull(), { timeout: 5000 });

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "coverage" } });
    fireEvent.click(screen.getByText("Search", { selector: "button" }));

    await waitFor(
      () =>
        expect(
          document.querySelectorAll('[data-hit-type="transcript_caption"]').length,
        ).toBeGreaterThan(0),
      { timeout: 5000 },
    );
    expect(screen.getAllByText(/not an addressable entity/).length).toBeGreaterThan(0);
  });

  it("walks a caption hit into the reader and lands on the caption (D-069)", async () => {
    // Scenario 2 of canvas plan section 17.3, end to end against the real
    // server: search a transcript phrase, follow the hit, arrive at the
    // timestamp. Before D-069 the click landed on Overview with the offset
    // discarded, and only the external YouTube link preserved it -- which
    // answers "jump to the timestamp" by leaving the application.
    window.location.hash = "#/";
    render(<App />);
    await waitFor(() => expect(screen.getByLabelText("Search")).not.toBeNull(), { timeout: 5000 });

    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "coverage" } });
    fireEvent.click(screen.getByText("Search", { selector: "button" }));
    await waitFor(
      () =>
        expect(
          document.querySelectorAll('[data-hit-type="transcript_caption"]').length,
        ).toBeGreaterThan(0),
      { timeout: 5000 },
    );

    const hit = document.querySelector('[data-hit-type="transcript_caption"]');
    // `#/sources/...` here, not `/sources/...`: this is the real `HashRouter`
    // (D-060), while the component tests mount `MemoryRouter` and see the
    // path without the fragment. Matching both is the point of running this
    // one against the app as it actually ships.
    const internal = [...(hit?.querySelectorAll("a") ?? [])].find((anchor) =>
      /^#?\/sources\//.test(anchor.getAttribute("href") ?? ""),
    );
    expect(internal, "the hit offers no link into the reader").toBeDefined();
    expect(internal?.getAttribute("href")).toContain("tab=transcript");
    expect(internal?.getAttribute("href")).toContain("t=");

    fireEvent.click(internal as Element, { button: 0 });

    // The transcript tab, not Overview, and the caption marked rather than the
    // top of the list.
    await waitFor(
      () => expect(document.querySelectorAll('[data-linked="true"]').length).toBe(1),
      { timeout: 5000 },
    );
    const marked = document.querySelector('[data-linked="true"]');
    expect(marked?.getAttribute("aria-current")).toBe("location");
    expect(marked?.textContent?.toLowerCase()).toContain("coverage");
  });
});
